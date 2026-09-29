from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import engine, get_db, Base
from models import Transaction, FraudAlert
from ml.predict import predict_fraud


# Create database tables
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="AI-Based Fraud Detection System",
    description="Backend API for detecting fraudulent transactions",
    version="1.0.0"
)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------
# Transaction request model
# -----------------------------------------

class TransactionCreate(BaseModel):
    transaction_id: str
    amount: float
    location: Optional[str] = None
    transaction_type: Optional[str] = None
    device_id: Optional[str] = None
    customer_id: Optional[str] = None
    failed_attempts: int = 0


# -----------------------------------------
# HOME
# -----------------------------------------

@app.get("/")
def root():
    return {
        "message": "AI-Based Fraud Detection System API is running",
        "status": "success"
    }


# -----------------------------------------
# HEALTH
# -----------------------------------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "system": "AI Fraud Detection"
    }


# -----------------------------------------
# DASHBOARD
# -----------------------------------------

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):

    total_transactions = db.query(Transaction).count()

    fraud_detected = (
        db.query(Transaction)
        .filter(Transaction.is_fraud == True)
        .count()
    )

    legitimate_transactions = (
        db.query(Transaction)
        .filter(Transaction.is_fraud == False)
        .count()
    )

    if total_transactions > 0:
        fraud_rate = round(
            (fraud_detected / total_transactions) * 100,
            2
        )
    else:
        fraud_rate = 0

    return {
        "total_transactions": total_transactions,
        "fraud_detected": fraud_detected,
        "legitimate_transactions": legitimate_transactions,
        "fraud_rate": fraud_rate
    }


# -----------------------------------------
# CREATE TRANSACTION
# -----------------------------------------

@app.post("/api/transactions")
def create_transaction(
    transaction_data: TransactionCreate,
    db: Session = Depends(get_db)
):

    # Check duplicate transaction
    existing_transaction = (
        db.query(Transaction)
        .filter(
            Transaction.transaction_id
            == transaction_data.transaction_id
        )
        .first()
    )

    if existing_transaction:
        raise HTTPException(
            status_code=400,
            detail="Transaction ID already exists"
        )

    # Current hour
    current_hour = datetime.now().hour

    # First version: assume new device
    new_device = 1

    # Run AI fraud prediction
    ai_result = predict_fraud(
        amount=transaction_data.amount,
        failed_attempts=transaction_data.failed_attempts,
        transaction_hour=current_hour,
        new_device=new_device
    )

    # Determine fraud status
    is_fraud = ai_result["prediction"] == "FRAUD"

    # Create transaction
    new_transaction = Transaction(
        transaction_id=transaction_data.transaction_id,
        amount=transaction_data.amount,
        location=transaction_data.location,
        transaction_type=transaction_data.transaction_type,
        device_id=transaction_data.device_id,
        customer_id=transaction_data.customer_id,
        failed_attempts=transaction_data.failed_attempts,
        is_fraud=is_fraud,
        fraud_score=ai_result["fraud_probability"]
    )

    # Add transaction to database
    db.add(new_transaction)

    # -----------------------------------------
    # CREATE FRAUD ALERT
    # -----------------------------------------

    alert_created = False

    if ai_result["risk_level"] in ["MEDIUM", "HIGH"]:

        alert = FraudAlert(
            transaction_id=transaction_data.transaction_id,
            risk_level=ai_result["risk_level"],
            fraud_probability=ai_result["fraud_probability"],
            message=(
                "Suspicious transaction detected. "
                "AI fraud probability: "
                f"{ai_result['fraud_probability']}%"
            ),
            status="NEW"
        )

        db.add(alert)

        alert_created = True

    # Save everything
    db.commit()

    # Refresh transaction
    db.refresh(new_transaction)

    return {
        "message": "Transaction analyzed successfully",

        "transaction": {
            "transaction_id": new_transaction.transaction_id,
            "amount": new_transaction.amount,
            "prediction": ai_result["prediction"],
            "fraud_probability": ai_result["fraud_probability"],
            "risk_level": ai_result["risk_level"]
        },

        "alert_created": alert_created
    }


# -----------------------------------------
# GET ALL TRANSACTIONS
# -----------------------------------------

@app.get("/api/transactions")
def get_transactions(
    db: Session = Depends(get_db)
):

    transactions = (
        db.query(Transaction)
        .order_by(Transaction.id.desc())
        .all()
    )

    return transactions


# -----------------------------------------
# GET ONE TRANSACTION
# -----------------------------------------

@app.get("/api/transactions/{transaction_id}")
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):

    transaction = (
        db.query(Transaction)
        .filter(
            Transaction.transaction_id == transaction_id
        )
        .first()
    )

    if not transaction:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found"
        )

    return transaction


# -----------------------------------------
# AI PREDICTION
# -----------------------------------------

@app.post("/api/predict")
def predict_transaction(
    transaction_data: TransactionCreate
):

    current_hour = datetime.now().hour

    new_device = 1

    result = predict_fraud(
        amount=transaction_data.amount,
        failed_attempts=transaction_data.failed_attempts,
        transaction_hour=current_hour,
        new_device=new_device
    )

    return {
        "transaction_id": transaction_data.transaction_id,
        "amount": transaction_data.amount,
        "prediction": result["prediction"],
        "fraud_probability": result["fraud_probability"],
        "risk_level": result["risk_level"]
    }


# -----------------------------------------
# GET FRAUD ALERTS
# -----------------------------------------

@app.get("/api/alerts")
def get_alerts(
    db: Session = Depends(get_db)
):

    alerts = (
        db.query(FraudAlert)
        .order_by(FraudAlert.id.desc())
        .all()
    )

    return alerts
# -----------------------------------------
# UPDATE FRAUD ALERT STATUS
# -----------------------------------------

@app.put("/api/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    status: str,
    db: Session = Depends(get_db)
):

    alert = (
        db.query(FraudAlert)
        .filter(FraudAlert.id == alert_id)
        .first()
    )

    if not alert:
        raise HTTPException(
            status_code=404,
            detail="Alert not found"
        )

    allowed_statuses = [
        "NEW",
        "REVIEWED",
        "RESOLVED"
    ]

    if status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Invalid alert status"
        )

    alert.status = status

    db.commit()
    db.refresh(alert)

    return {
        "message": "Alert status updated successfully",
        "alert": alert
    }