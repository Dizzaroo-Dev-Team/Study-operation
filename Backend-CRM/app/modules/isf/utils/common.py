from pydantic_core import core_schema
from bson import ObjectId


class PyObjectId(ObjectId):
    """Custom ObjectId validator for Pydantic v2"""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        return core_schema.no_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(cls, schema, handler):
        # OpenAPI / `app.openapi()` calls this for any field typed as PyObjectId.
        # Without it, FastAPI's schema generation raises PydanticInvalidForJsonSchema.
        return {"type": "string", "example": "507f1f77bcf86cd799439011"}

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)
