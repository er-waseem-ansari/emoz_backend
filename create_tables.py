from app.database import Base, engine
from app.models.otp import OTPVerification
from app.models.user import User
from app.models.token import RefreshToken

# Create all tables
Base.metadata.create_all(bind=engine)
print("Tables created successfully!")