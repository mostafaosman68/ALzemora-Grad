from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    profile_image = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    status = Column(String, nullable=True)
    address = Column(String, nullable=True)
    emergency_contacts = Column(Text, nullable=True)   # JSON string
    dnr_status = Column(Boolean, default=False)
    last_medical_report = Column(String, nullable=True)
    last_location = Column(Text, nullable=True)        # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)

    people = relationship("Person", back_populates="user", cascade="all, delete-orphan")
    medications = relationship("Medication", back_populates="user", cascade="all, delete-orphan")
    location_history = relationship("LocationHistory", back_populates="user", cascade="all, delete-orphan")
    guardians = relationship("Guardian", back_populates="user", cascade="all, delete-orphan")
    caregivers = relationship("Caregiver", back_populates="user", cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    relation = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    voice = Column(String, nullable=True)
    permissions = Column(Text, nullable=True)          # JSON string
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    face_embedding = Column(Text, nullable=True)       # JSON string
    voice_embedding = Column(Text, nullable=True)      # JSON string

    user = relationship("User", back_populates="people")


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    schedule = Column(Text, nullable=True)             # JSON string
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    user = relationship("User", back_populates="medications")


class LocationHistory(Base):
    __tablename__ = "location_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    location = Column(Text, nullable=True)             # JSON string
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="location_history")


class Guardian(Base):
    __tablename__ = "guardians"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    priority = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="guardians")


class Caregiver(Base):
    __tablename__ = "caregivers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    agency = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="caregivers")