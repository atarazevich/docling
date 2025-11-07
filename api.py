"""
FastAPI service wrapper for Docling document converter
Provides REST API endpoints for document conversion to Markdown/JSON
"""

import os
import time
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
import tempfile
import httpx
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, HttpUrl
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response

from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PipelineOptions

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
conversion_counter = Counter('docling_conversions_total', 'Total number of document conversions', ['format', 'status'])
conversion_duration = Histogram('docling_conversion_duration_seconds', 'Duration of document conversions')
active_conversions = Counter('docling_active_conversions', 'Number of currently active conversions')

# Initialize FastAPI app
app = FastAPI(
    title="Docling API",
    description="Document parsing and conversion service powered by Docling",
    version="2.61.1",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Initialize converter globally (expensive initialization)
try:
    logger.info("Initializing Docling DocumentConverter...")
    converter = DocumentConverter()
    logger.info("DocumentConverter initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize DocumentConverter: {e}")
    converter = None


class OutputFormat(str, Enum):
    """Supported output formats"""
    markdown = "markdown"
    json = "json"
    doctags = "doctags"
    text = "text"


class ConvertRequest(BaseModel):
    """Request model for URL-based conversion"""
    url: HttpUrl = Field(..., description="URL of the document to convert")
    output_format: OutputFormat = Field(
        OutputFormat.markdown,
        description="Output format for the conversion"
    )
    ocr_enabled: bool = Field(
        True,
        description="Enable OCR for scanned documents"
    )
    table_extraction: bool = Field(
        True,
        description="Enable table structure extraction"
    )
    formula_extraction: bool = Field(
        True,
        description="Enable formula extraction"
    )


class ConvertResponse(BaseModel):
    """Response model for conversion results"""
    status: str = Field(..., description="Conversion status")
    format: str = Field(..., description="Output format used")
    content: Optional[str] = Field(None, description="Converted content (for text formats)")
    document: Optional[Dict[str, Any]] = Field(None, description="Document object (for JSON format)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Conversion metadata")
    duration_seconds: float = Field(..., description="Time taken for conversion")


@app.get("/", response_class=PlainTextResponse)
async def root():
    """Root endpoint with service information"""
    return """Docling API Service

Document parsing and conversion service powered by Docling.
Visit /docs for interactive API documentation.

Endpoints:
- POST /convert - Convert document from URL
- POST /convert/upload - Convert uploaded document file
- GET /health - Health check
- GET /metrics - Prometheus metrics
"""


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if converter is None:
        raise HTTPException(status_code=503, detail="DocumentConverter not initialized")

    return {
        "status": "healthy",
        "service": "docling-api",
        "version": "2.61.1",
        "converter_ready": converter is not None
    }


@app.get("/metrics", response_class=Response)
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/convert", response_model=ConvertResponse)
async def convert_from_url(request: ConvertRequest):
    """
    Convert a document from URL to specified format

    Supports various document formats including PDF, DOCX, PPTX, XLSX, HTML, images, etc.
    """
    if converter is None:
        raise HTTPException(status_code=503, detail="DocumentConverter not initialized")

    start_time = time.time()
    active_conversions.inc()

    try:
        logger.info(f"Starting conversion for URL: {request.url}")

        # Configure pipeline options based on request
        pipeline_options = PipelineOptions()
        pipeline_options.do_ocr = request.ocr_enabled
        pipeline_options.do_table_structure = request.table_extraction

        # Convert the document
        with conversion_duration.time():
            result = converter.convert(
                str(request.url),
                pipeline_options=pipeline_options
            )

        # Export based on requested format
        if request.output_format == OutputFormat.markdown:
            content = result.document.export_to_markdown()
            response_data = {
                "status": "success",
                "format": "markdown",
                "content": content,
                "metadata": {
                    "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                    "source": str(request.url)
                }
            }
        elif request.output_format == OutputFormat.json:
            doc_dict = result.document.export_to_dict()
            response_data = {
                "status": "success",
                "format": "json",
                "document": doc_dict,
                "metadata": {
                    "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                    "source": str(request.url)
                }
            }
        elif request.output_format == OutputFormat.doctags:
            content = result.document.export_to_doctags()
            response_data = {
                "status": "success",
                "format": "doctags",
                "content": content,
                "metadata": {
                    "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                    "source": str(request.url)
                }
            }
        else:  # text
            content = result.document.export_to_text()
            response_data = {
                "status": "success",
                "format": "text",
                "content": content,
                "metadata": {
                    "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                    "source": str(request.url)
                }
            }

        duration = time.time() - start_time
        response_data["duration_seconds"] = duration

        conversion_counter.labels(format=request.output_format, status="success").inc()
        logger.info(f"Conversion completed successfully in {duration:.2f}s")

        return ConvertResponse(**response_data)

    except Exception as e:
        conversion_counter.labels(format=request.output_format, status="error").inc()
        logger.error(f"Conversion failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
    finally:
        active_conversions.dec()


@app.post("/convert/upload", response_model=ConvertResponse)
async def convert_from_upload(
    file: UploadFile = File(..., description="Document file to convert"),
    output_format: OutputFormat = Form(OutputFormat.markdown),
    ocr_enabled: bool = Form(True),
    table_extraction: bool = Form(True),
    formula_extraction: bool = Form(True)
):
    """
    Convert an uploaded document file to specified format

    Supports various document formats including PDF, DOCX, PPTX, XLSX, HTML, images, etc.
    """
    if converter is None:
        raise HTTPException(status_code=503, detail="DocumentConverter not initialized")

    start_time = time.time()
    active_conversions.inc()

    # Validate file size (max 100MB)
    if file.size > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File size exceeds 100MB limit")

    try:
        logger.info(f"Starting conversion for uploaded file: {file.filename}")

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name

        try:
            # Configure pipeline options
            pipeline_options = PipelineOptions()
            pipeline_options.do_ocr = ocr_enabled
            pipeline_options.do_table_structure = table_extraction

            # Convert the document
            with conversion_duration.time():
                result = converter.convert(
                    tmp_file_path,
                    pipeline_options=pipeline_options
                )

            # Export based on requested format
            if output_format == OutputFormat.markdown:
                content = result.document.export_to_markdown()
                response_data = {
                    "status": "success",
                    "format": "markdown",
                    "content": content,
                    "metadata": {
                        "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                        "filename": file.filename,
                        "file_size": file.size
                    }
                }
            elif output_format == OutputFormat.json:
                doc_dict = result.document.export_to_dict()
                response_data = {
                    "status": "success",
                    "format": "json",
                    "document": doc_dict,
                    "metadata": {
                        "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                        "filename": file.filename,
                        "file_size": file.size
                    }
                }
            elif output_format == OutputFormat.doctags:
                content = result.document.export_to_doctags()
                response_data = {
                    "status": "success",
                    "format": "doctags",
                    "content": content,
                    "metadata": {
                        "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                        "filename": file.filename,
                        "file_size": file.size
                    }
                }
            else:  # text
                content = result.document.export_to_text()
                response_data = {
                    "status": "success",
                    "format": "text",
                    "content": content,
                    "metadata": {
                        "page_count": len(result.document.pages) if hasattr(result.document, 'pages') else 0,
                        "filename": file.filename,
                        "file_size": file.size
                    }
                }

            duration = time.time() - start_time
            response_data["duration_seconds"] = duration

            conversion_counter.labels(format=output_format, status="success").inc()
            logger.info(f"Conversion completed successfully in {duration:.2f}s")

            return ConvertResponse(**response_data)

        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_file_path)
            except:
                pass

    except Exception as e:
        conversion_counter.labels(format=output_format, status="error").inc()
        logger.error(f"Conversion failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {str(e)}")
    finally:
        active_conversions.dec()


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    logger.info("Docling API service starting up...")
    if converter is None:
        logger.error("WARNING: DocumentConverter failed to initialize during startup")
    else:
        logger.info("Service ready to accept requests")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown"""
    logger.info("Docling API service shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")