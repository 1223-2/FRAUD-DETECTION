from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from datetime import datetime

from database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)

    transaction_id = Column(String, unique=True, index=True)
    amount = Column(Float, nullable=False)

    location = Column(String)
    transaction_type = Column(String)

    device_id = Column(String)
    customer_id = Column(String)

    failed_attempts = Column(Integer, default=0)

    is_fraud = Column(Boolean, default=False)

    fraud_score = Column(Float, default=0.0)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(Integer, primary_key=True, index=True)

    transaction_id = Column(String, index=True)

    risk_level = Column(String)

    fraud_probability = Column(Float)

    message = Column(String)

    status = Column(
        String,
        default="NEW"
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )