"""
Script to sync tables from local PostgreSQL database to Neon PostgreSQL database.
This script will:
1. Connect to both local and Neon databases
2. Compare table lists
3. Extract table definitions from local database
4. Create missing tables in Neon database
"""
import asyncio
import sys
import os
from sqlalchemy import text, create_engine, inspect
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from urllib.parse import urlparse
import subprocess


def get_table_ddl_sync(connection_string: str, table_name: str) -> str:
    """
    Get the CREATE TABLE DDL for a specific table using pg_dump.
    This is the most reliable way to get exact table definitions.
    """
    try:
        # Parse connection string
        parsed = urlparse(connection_string.replace("postgresql+asyncpg://", "postgresql://"))
        
        # Build pg_dump command
        cmd = [
            "pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--table", f"public.{table_name}",
            "--dbname", parsed.path[1:] if parsed.path.startswith("/") else parsed.path,
        ]
        
        if parsed.hostname:
            cmd.extend(["--host", parsed.hostname])
        if parsed.port:
            cmd.extend(["--port", str(parsed.port)])
        if parsed.username:
            cmd.extend(["--username", parsed.username])
        
        # Set password via environment variable
        env = os.environ.copy()
        if parsed.password:
            env["PGPASSWORD"] = parsed.password
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=30
        )
        
        if result.returncode != 0:
            raise Exception(f"pg_dump failed: {result.stderr}")
        
        return result.stdout
    except FileNotFoundError:
        raise Exception("pg_dump not found. Please install PostgreSQL client tools.")
    except Exception as e:
        raise Exception(f"Failed to get DDL using pg_dump: {e}")


async def get_table_ddl_async(session: AsyncSession, table_name: str) -> str:
    """
    Get the CREATE TABLE DDL for a specific table using SQL queries.
    This is a fallback method if pg_dump is not available.
    """
    # Get column definitions
    columns_query = text("""
        SELECT 
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default,
            udt_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table_name
        ORDER BY ordinal_position
    """)
    
    result = await session.execute(columns_query, {"table_name": table_name})
    columns = result.fetchall()
    
    if not columns:
        return None
    
    # Get constraints (primary keys, foreign keys, unique constraints)
    pk_query = text("""
        SELECT column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_schema = 'public' 
        AND tc.table_name = :table_name
        AND tc.constraint_type = 'PRIMARY KEY'
    """)
    
    pk_result = await session.execute(pk_query, {"table_name": table_name})
    pk_columns = [row[0] for row in pk_result.fetchall()]
    
    # Get foreign keys
    fk_query = text("""
        SELECT
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name,
            rc.update_rule,
            rc.delete_rule
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        JOIN information_schema.referential_constraints AS rc
            ON tc.constraint_name = rc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
        AND tc.table_name = :table_name
    """)
    
    fk_result = await session.execute(fk_query, {"table_name": table_name})
    foreign_keys = fk_result.fetchall()
    
    # Build CREATE TABLE statement
    column_defs = []
    for col in columns:
        col_name = col.column_name
        data_type = col.data_type
        max_length = col.character_maximum_length
        is_nullable = col.is_nullable == "YES"
        default = col.column_default
        
        # Map data types
        if data_type == "character varying" or data_type == "varchar":
            type_str = f"VARCHAR({max_length})" if max_length else "VARCHAR"
        elif data_type == "character" or data_type == "char":
            type_str = f"CHAR({max_length})" if max_length else "CHAR"
        elif data_type == "text":
            type_str = "TEXT"
        elif data_type == "integer":
            type_str = "INTEGER"
        elif data_type == "bigint":
            type_str = "BIGINT"
        elif data_type == "smallint":
            type_str = "SMALLINT"
        elif data_type == "boolean":
            type_str = "BOOLEAN"
        elif data_type == "timestamp with time zone":
            type_str = "TIMESTAMP WITH TIME ZONE"
        elif data_type == "timestamp without time zone":
            type_str = "TIMESTAMP"
        elif data_type == "date":
            type_str = "DATE"
        elif data_type == "time":
            type_str = "TIME"
        elif data_type == "numeric":
            type_str = "NUMERIC"
        elif data_type == "double precision":
            type_str = "DOUBLE PRECISION"
        elif data_type == "real":
            type_str = "REAL"
        elif data_type == "json" or data_type == "jsonb":
            type_str = "JSONB" if data_type == "jsonb" else "JSON"
        elif data_type == "uuid":
            type_str = "UUID"
        elif data_type == "ARRAY":
            type_str = f"{col.udt_name}[]"
        elif data_type == "USER-DEFINED":
            # For enums and custom types
            type_str = col.udt_name
        else:
            type_str = data_type.upper()
        
        col_def = f"{col_name} {type_str}"
        
        if not is_nullable:
            col_def += " NOT NULL"
        
        if default:
            # Clean up default value
            default_str = str(default)
            if default_str.startswith("nextval"):
                col_def += f" DEFAULT {default_str}"
            elif default_str.startswith("gen_random_uuid()"):
                col_def += " DEFAULT gen_random_uuid()"
            elif default_str.startswith("CURRENT_TIMESTAMP"):
                col_def += " DEFAULT CURRENT_TIMESTAMP"
            else:
                col_def += f" DEFAULT {default_str}"
        
        column_defs.append(col_def)
    
    # Add primary key constraint
    if pk_columns:
        column_defs.append(f"PRIMARY KEY ({', '.join(pk_columns)})")
    
    # Add foreign key constraints
    for fk in foreign_keys:
        col_name, ref_table, ref_col, update_rule, delete_rule = fk
        fk_def = f"FOREIGN KEY ({col_name}) REFERENCES {ref_table}({ref_col})"
        if update_rule and update_rule != "NO ACTION":
            fk_def += f" ON UPDATE {update_rule}"
        if delete_rule and delete_rule != "NO ACTION":
            fk_def += f" ON DELETE {delete_rule}"
        column_defs.append(fk_def)
    
    create_sql = f"CREATE TABLE {table_name} (\n    " + ",\n    ".join(column_defs) + "\n)"
    
    return create_sql


async def get_table_list(session: AsyncSession) -> list:
    """Get list of all tables in the database."""
    query = text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def sync_tables():
    """Main function to sync tables from local to Neon."""
    print("=" * 70)
    print("Database Table Synchronization: Local → Neon")
    print("=" * 70)
    print()
    
    # Get connection strings (check LOCAL_DATABASE_URL first, fallback to DATABASE_URL)
    local_db_url = os.getenv("LOCAL_DATABASE_URL") or os.getenv("DATABASE_URL")
    neon_db_url = os.getenv("NEON_DATABASE_URL")
    
    if not local_db_url:
        print("❌ ERROR: LOCAL_DATABASE_URL or DATABASE_URL environment variable not set")
        print("   Example: postgresql+asyncpg://user:pass@localhost:5432/dbname")
        sys.exit(1)
    
    if not neon_db_url:
        print("❌ ERROR: NEON_DATABASE_URL environment variable not set")
        print("   Example: postgresql+asyncpg://user:pass@neon-host/dbname")
        print("\n💡 Set it with: set NEON_DATABASE_URL=your-neon-connection-string")
        sys.exit(1)
    
    print(f"📊 Local Database: {local_db_url.split('@')[-1] if '@' in local_db_url else local_db_url}")
    print(f"☁️  Neon Database: {neon_db_url.split('@')[-1] if '@' in neon_db_url else neon_db_url}")
    print()
    
    # Create engines
    local_engine = create_async_engine(local_db_url, echo=False)
    neon_engine = create_async_engine(neon_db_url, echo=False)
    
    local_session_maker = async_sessionmaker(local_engine, class_=AsyncSession, expire_on_commit=False)
    neon_session_maker = async_sessionmaker(neon_engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        # Get table lists
        print("🔍 Comparing table lists...")
        async with local_session_maker() as local_session:
            local_tables = await get_table_list(local_session)
        
        async with neon_session_maker() as neon_session:
            neon_tables = await get_table_list(neon_session)
        
        print(f"   Local database has {len(local_tables)} tables")
        print(f"   Neon database has {len(neon_tables)} tables")
        print()
        
        # Find missing tables
        missing_tables = [t for t in local_tables if t not in neon_tables]
        
        if not missing_tables:
            print("✅ All tables already exist in Neon database!")
            return
        
        print(f"📋 Found {len(missing_tables)} missing tables:")
        for table in missing_tables:
            print(f"   - {table}")
        print()
        
        # Try to use pg_dump first, fallback to SQL queries
        use_pg_dump = True
        try:
            # Test if pg_dump is available
            proc = await asyncio.create_subprocess_exec(
                "pg_dump", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=5)
        except (FileNotFoundError, subprocess.TimeoutError):
            use_pg_dump = False
            print("⚠️  pg_dump not available, using SQL queries instead")
            print()
        
        # Create missing tables
        print("🔨 Creating missing tables in Neon...")
        print()
        
        created_count = 0
        failed_tables = []
        
        for table_name in missing_tables:
            try:
                print(f"   Creating table '{table_name}'...", end=" ")
                
                # Get table DDL
                if use_pg_dump:
                    try:
                        ddl = get_table_ddl_sync(local_db_url, table_name)
                        # Extract just the CREATE TABLE statement
                        lines = ddl.split('\n')
                        create_lines = []
                        in_create = False
                        for line in lines:
                            if 'CREATE TABLE' in line.upper():
                                in_create = True
                            if in_create:
                                create_lines.append(line)
                                if line.strip().endswith(';') and 'CREATE TABLE' in '\n'.join(create_lines):
                                    break
                        ddl = '\n'.join(create_lines)
                    except Exception as e:
                        print(f"\n      ⚠️  pg_dump failed: {e}, trying SQL method...")
                        async with local_session_maker() as local_session:
                            ddl = await get_table_ddl_async(local_session, table_name)
                else:
                    async with local_session_maker() as local_session:
                        ddl = await get_table_ddl_async(local_session, table_name)
                
                if not ddl:
                    print(f"❌ Could not get DDL for table '{table_name}'")
                    failed_tables.append(table_name)
                    continue
                
                # Execute on Neon
                async with neon_session_maker() as neon_session:
                    # Remove trailing semicolon if present
                    ddl_clean = ddl.strip().rstrip(';')
                    await neon_session.execute(text(ddl_clean))
                    await neon_session.commit()
                
                print("✅")
                created_count += 1
                
            except Exception as e:
                print(f"❌ Error: {e}")
                failed_tables.append(table_name)
                async with neon_session_maker() as neon_session:
                    await neon_session.rollback()
        
        print()
        print("=" * 70)
        if created_count > 0:
            print(f"✅ Successfully created {created_count} table(s)")
        if failed_tables:
            print(f"❌ Failed to create {len(failed_tables)} table(s): {', '.join(failed_tables)}")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await local_engine.dispose()
        await neon_engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(sync_tables())
    except KeyboardInterrupt:
        print("\n\n⚠️  Synchronization interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
