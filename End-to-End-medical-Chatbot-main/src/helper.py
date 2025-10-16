"""
Medical Document Processing Helper Functions

This module provides comprehensive utility functions for processing medical documents
and initializing AI components for the medical chatbot system. It includes functions
for PDF document loading, text chunking, and embedding model initialization with
medical domain optimization.

The functions are designed to work with medical literature and provide efficient
document retrieval for the RAG (Retrieval-Augmented Generation) system.
"""

import logging
import os
from typing import List, Optional, Any
from pathlib import Path

# Document processing imports
import PyPDF2
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain.document_loaders import PyPDFLoader, DirectoryLoader
# from langchain.embeddings import HuggingFaceEmbeddings

# HuggingFace and embedding imports
from langchain_huggingface import HuggingFaceEmbeddings

# Configure logging for this module
logger = logging.getLogger(__name__)


def load_medical_documents_from_directory(data_directory: str = "Documents/") -> List[Document]:
    """
    Load and extract text from all PDF documents in the specified directory.
    
    This function processes all PDF files in the given directory and extracts
    their text content for use in the medical knowledge base. Each document
    is converted into a LangChain Document object with metadata.
    
    Args:
        data_directory (str): Path to directory containing medical PDF documents.
                             Defaults to "Documents/"
    
    Returns:
        List[Document]: List of LangChain Document objects containing extracted text
                       and metadata from the PDF files
    
    Raises:
        FileNotFoundError: If the specified directory doesn't exist
        Exception: If there are issues reading PDF files

    """
    try:
        logger.info(f"Loading medical documents from directory: {data_directory}")
        
        # Validate directory exists
        data_path = Path(data_directory)
        if not data_path.exists():
            raise FileNotFoundError(f"Directory not found: {data_directory}")
        
        if not data_path.is_dir():
            raise ValueError(f"Path is not a directory: {data_directory}")
        
        # Find all PDF files in the directory
        pdf_files = list(data_path.glob("*.pdf"))
        
        if not pdf_files:
            logger.warning(f"No PDF files found in directory: {data_directory}")
            return []
        
        logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        extracted_documents = []
        
        # Process each PDF file
        for pdf_file_path in pdf_files:
            try:
                logger.info(f"Processing medical document: {pdf_file_path.name}")
                
                with open(pdf_file_path, 'rb') as pdf_file:
                    # Initialize PDF reader
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    
                    # Extract text from all pages
                    document_text = ""
                    for page_number, page in enumerate(pdf_reader.pages):
                        try:
                            page_text = page.extract_text()
                            if page_text.strip():  # Only add non-empty pages
                                document_text += page_text + "\n\n"
                        except Exception as page_error:
                            logger.warning(f"Error extracting text from page {page_number + 1} "
                                         f"in {pdf_file_path.name}: {str(page_error)}")
                            continue
                    
                    # Create Document object with metadata
                    if document_text.strip():
                        document = Document(
                            page_content=document_text.strip(),
                            metadata={
                                "source": str(pdf_file_path),
                                "filename": pdf_file_path.name,
                                "document_type": "medical_pdf",
                                "page_count": len(pdf_reader.pages)
                            }
                        )
                        extracted_documents.append(document)
                        logger.info(f"Successfully extracted {len(document_text)} characters "
                                  f"from {pdf_file_path.name}")
                    else:
                        logger.warning(f"No text content extracted from {pdf_file_path.name}")
                        
            except Exception as file_error:
                logger.error(f"Error processing PDF file {pdf_file_path.name}: {str(file_error)}")
                continue
        
        logger.info(f"Successfully loaded {len(extracted_documents)} medical documents")
        
        if not extracted_documents:
            logger.warning("No documents were successfully processed")
        
        return extracted_documents
        
    except Exception as error:
        logger.error(f"Error loading medical documents from directory: {str(error)}")
        raise


def split_documents_into_semantic_chunks(
    documents: List[Document], 
    chunk_size: int = 500, 
    chunk_overlap: int = 50
) -> List[Document]:
    """
    Split documents into smaller, semantically meaningful chunks for vector storage.
    
    This function takes large medical documents and splits them into smaller chunks
    that are optimal for vector embedding and retrieval. The chunking preserves
    semantic meaning while ensuring chunks are appropriately sized for the embedding model.
    
    Args:
        documents (List[Document]): List of Document objects to be chunked
        chunk_size (int): Maximum size of each text chunk in characters. 
                         Defaults to 500 for optimal embedding performance
        chunk_overlap (int): Number of characters to overlap between chunks.
                           Defaults to 50 to maintain context continuity
    
    Returns:
        List[Document]: List of smaller Document chunks with preserved metadata
    
    Raises:
        ValueError: If chunk_size or chunk_overlap parameters are invalid
        Exception: If there are issues during text splitting
    """
    try:
        logger.info(f"Splitting {len(documents)} documents into semantic chunks")
        logger.info(f"Chunk parameters: size={chunk_size}, overlap={chunk_overlap}")
        
        # Validate parameters
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        
        if not documents:
            logger.warning("No documents provided for chunking")
            return []
        
        # Initialize the text splitter with medical-optimized settings
        medical_text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=[
                "\n\n",  # Paragraph breaks (highest priority)
                "\n",    # Line breaks
                ". ",    # Sentence endings
                "? ",    # Question endings
                "! ",    # Exclamation endings
                "; ",    # Semicolon breaks
                ", ",    # Comma breaks
                " ",     # Word breaks
                ""       # Character breaks (fallback)
            ],
            keep_separator=True,
            add_start_index=True
        )
        
        all_document_chunks = []
        
        # Process each document
        for doc_index, document in enumerate(documents):
            try:
                logger.debug(f"Chunking document {doc_index + 1}: "
                           f"{document.metadata.get('filename', 'Unknown')}")
                
                # Split the document into chunks
                document_chunks = medical_text_splitter.split_documents([document])
                
                # Enhance metadata for each chunk
                for chunk_index, chunk in enumerate(document_chunks):
                    # Preserve original metadata and add chunk-specific information
                    enhanced_metadata = document.metadata.copy()
                    enhanced_metadata.update({
                        "chunk_index": chunk_index,
                        "total_chunks": len(document_chunks),
                        "chunk_size": len(chunk.page_content),
                        "parent_document_index": doc_index
                    })
                    chunk.metadata = enhanced_metadata
                
                all_document_chunks.extend(document_chunks)
                
                logger.debug(f"Created {len(document_chunks)} chunks from document "
                           f"{document.metadata.get('filename', 'Unknown')}")
                
            except Exception as doc_error:
                logger.error(f"Error chunking document {doc_index + 1}: {str(doc_error)}")
                continue
        
        logger.info(f"Successfully created {len(all_document_chunks)} semantic chunks")
        
        # Log statistics
        if all_document_chunks:
            chunk_sizes = [len(chunk.page_content) for chunk in all_document_chunks]
            avg_chunk_size = sum(chunk_sizes) / len(chunk_sizes)
            logger.info(f"Average chunk size: {avg_chunk_size:.1f} characters")
            logger.info(f"Chunk size range: {min(chunk_sizes)} - {max(chunk_sizes)} characters")
        
        return all_document_chunks
        
    except Exception as error:
        logger.error(f"Error splitting documents into chunks: {str(error)}")
        raise


def initialize_medical_embedding_model(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
) -> Optional[HuggingFaceEmbeddings]:
    """
    Initialize and configure the HuggingFace embeddings model for medical text processing.
    
    This function sets up the sentence transformer model that converts medical text
    into vector embeddings for semantic similarity search. The model is optimized
    for medical domain text processing and efficient vector operations.
    
    Args:
        model_name (str): Name of the HuggingFace sentence transformer model.
                         Defaults to "sentence-transformers/all-MiniLM-L6-v2"
                         which provides good performance for medical text
    
    Returns:
        Optional[HuggingFaceEmbeddings]: Initialized embeddings model,
                                       or None if initialization fails
    
    Raises:
        Exception: If there are issues downloading or initializing the model
    """
    try:
        logger.info(f"Initializing medical embeddings model: {model_name}")
        
        # Configure model parameters for medical text processing
        model_configuration = {
            "model_name": model_name,
            "model_kwargs": {
                "device": "cpu",  # Use CPU for compatibility across systems
                "trust_remote_code": False  # Security setting
            },
            "encode_kwargs": {
                "normalize_embeddings": True,  # Normalize vectors for cosine similarity
                "batch_size": 32  # Process multiple texts efficiently
            }
        }
        
        # Initialize the HuggingFace embeddings model
        medical_embeddings = HuggingFaceEmbeddings(**model_configuration)
        
        # Test the model with a sample medical query
        test_query = "What are the common symptoms of hypertension?"
        try:
            test_embedding = medical_embeddings.embed_query(test_query)
            embedding_dimension = len(test_embedding)
            logger.info(f"Medical embeddings model initialized successfully")
            logger.info(f"Embedding dimension: {embedding_dimension}")
            logger.info(f"Model ready for medical text processing")
            
        except Exception as test_error:
            logger.error(f"Model initialization test failed: {str(test_error)}")
            return None
        
        return medical_embeddings
        
    except Exception as error:
        logger.error(f"Failed to initialize medical embeddings model: {str(error)}")
        logger.error("Please check internet connection and model availability")
        return None


# Backward compatibility functions for existing code
def load_pdf_file(data: str = "Documents/") -> List[Document]:
    """
    Backward compatibility wrapper for load_medical_documents_from_directory.
    
    Args:
        data (str): Directory path containing PDF files
    
    Returns:
        List[Document]: Extracted documents
    """
    logger.warning("load_pdf_file() is deprecated. Use load_medical_documents_from_directory() instead.")
    return load_medical_documents_from_directory(data)


def text_split(extracted_data: List[Document]) -> List[Document]:
    """
    Backward compatibility wrapper for split_documents_into_semantic_chunks.
    
    Args:
        extracted_data (List[Document]): Documents to split
    
    Returns:
        List[Document]: Split document chunks
    """
    logger.warning("text_split() is deprecated. Use split_documents_into_semantic_chunks() instead.")
    return split_documents_into_semantic_chunks(extracted_data)


def hugging_face_embedding_model() -> Optional[HuggingFaceEmbeddings]:
    """
    Backward compatibility wrapper for initialize_medical_embedding_model.
    
    Returns:
        Optional[HuggingFaceEmbeddings]: Initialized embeddings model
    """
    logger.warning("hugging_face_embedding_model() is deprecated. Use initialize_medical_embedding_model() instead.")
    return initialize_medical_embedding_model()