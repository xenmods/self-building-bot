from motor.motor_asyncio import AsyncIOMotorClient
from Bot import LOGGER
from Bot.config import MONGO_URI, DB_NAME

# Initialize default values
client = None
db = None
users_collection = None

# Initialize MongoDB connection only if MONGO_URI is provided
if MONGO_URI:
    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client[DB_NAME]
        users_collection = db.users # sample users collection
        LOGGER.info("Successfully connected to MongoDB with Motor AsyncIO!")
    except Exception as e:
        LOGGER.error(f"Failed to connect to MongoDB: {e}")
        # Reset to default values in case of error
        client = None
        db = None
        users_collection = None
else:
    LOGGER.warning("MONGO_URI not set. MongoDB functionality will be disabled.")
