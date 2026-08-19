"""Shared SQLAlchemy type decorators used across model files."""
from sqlalchemy import String, TypeDecorator


class EnumValueType(TypeDecorator):
    """TypeDecorator that converts between Python enum instances and database enum string values."""
    impl = String
    cache_ok = True

    def __init__(self, enum_class, enum_type_name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enum_class = enum_class
        self.enum_type_name = enum_type_name

    def process_bind_param(self, value, dialect):
        """Convert enum instance to its string value for database storage."""
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        return str(value)

    def process_result_value(self, value, dialect):
        """Convert database string value back to enum instance."""
        if value is None:
            return None
        if isinstance(value, str):
            try:
                for enum_member in self.enum_class:
                    if enum_member.value == value:
                        return enum_member
                return self.enum_class(value)
            except ValueError:
                return value
        return value

    def load_dialect_impl(self, dialect):
        """Use String as base, but cast to enum type in SQL when needed."""
        return String(50)

    def bind_expression(self, bindvalue):
        """Explicitly cast string value to enum type in SQL for PostgreSQL."""
        from sqlalchemy.sql import cast
        from sqlalchemy.dialects.postgresql import ENUM
        return cast(bindvalue, ENUM(name=self.enum_type_name, create_type=False))
