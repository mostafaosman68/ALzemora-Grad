from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class MedScanDetectionItem(BaseModel):
	medicine_key: str
	name: str
	generic_name: Optional[str] = None
	category: Optional[str] = None
	dosage_form: Optional[str] = None
	strength: Optional[str] = None
	manufacturer: Optional[str] = None
	description: Optional[str] = None
	warnings: Optional[str] = None
	confidence: float = 0.0
	good_match_count: int = 0
	inlier_ratio: float = 0.0
	bbox: Optional[list[int]] = None
	ocr_matched: bool = False


class MedScanEventBase(BaseModel):
	patient_id: str
	actor_user_id: Optional[str] = None
	actor_role: Optional[str] = None
	image_name: Optional[str] = None
	image_path: Optional[str] = None
	status: str
	ocr_text: Optional[str] = None
	primary_medicine_key: Optional[str] = None
	primary_medicine_name: Optional[str] = None
	primary_confidence: float = 0.0
	detections: list[MedScanDetectionItem] = Field(default_factory=list)
	summary_text: Optional[str] = None
	created_at: Optional[datetime] = None


class MedScanUploadResponse(BaseModel):
	message: str
	event: MedScanEventBase


class MedScanHistoryResponse(BaseModel):
	patient_id: str
	count: int
	items: list[MedScanEventBase]


class MedicineCatalogItem(BaseModel):
	key: str
	name: str
	generic_name: str
	category: str
	dosage_form: str
	strength: str
	manufacturer: str
	description: str
	warnings: str


class MedicineCatalogResponse(BaseModel):
	count: int
	medicines: list[MedicineCatalogItem]
