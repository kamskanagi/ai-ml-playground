"""
Medical AI Chatbot Flask Application

This Flask web application provides a medical AI chatbot interface that uses 
Retrieval-Augmented Generation (RAG) to answer medical questions. The system combines:
- Groq or OPENAI API for fast language model inference (Meta Llama model)
- Pinecone vector database for medical document retrieval
- HuggingFace embeddings for semantic search
- Medical knowledge base from PDF documents

The application serves a modern web interface and provides REST API endpoints
for real-time medical question answering with contextual information.
"""

# Standard library imports
import os
import logging
from typing import Optional, Dict, Any, Tuple

# Third-party Flask and web framework imports
from flask import Flask, render_template, jsonify, request, abort
from dotenv import load_dotenv

# LangChain and AI model imports
from langchain_groq import ChatGroq
from langchain.chains import create_retrieval_chain
from langchain_pinecone import PineconeVectorStore
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

# Local module imports
from src.helper import initialize_medical_embedding_model
from src.prompt import system_prompt


# Configure logging for better debugging and monitoring
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask application with medical chatbot configuration
medical_chatbot_app = Flask(__name__)
medical_chatbot_app.config['SECRET_KEY'] = 'medical-ai-chatbot-secret-key'  # For session security

# Application configuration constants
MEDICAL_VECTOR_INDEX_NAME = "medicalchat"
SIMILARITY_SEARCH_RESULTS_COUNT = 3
LLM_TEMPERATURE = 0  # Deterministic responses for medical accuracy
GROQ_MODEL_NAME = "meta-llama/llama-4-scout-17b-16e-instruct"
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 8081

# Global variables for AI components (initialized during startup)
medical_embeddings_model: Optional[Any] = None
medical_document_retriever: Optional[Any] = None
medical_language_model: Optional[ChatGroq] = None
medical_rag_chain: Optional[Any] = None


def load_environment_configuration() -> Tuple[str, str]:
    """
    Load and validate environment variables for API keys and configuration.
    
    This function loads environment variables from .env file and validates
    that all required API keys are present for the medical chatbot to function.
    
    Returns:
        Tuple[str, str]: A tuple containing (pinecone_api_key, groq_api_key)
    
    Raises:
        EnvironmentError: If required API keys are missing from environment
        FileNotFoundError: If .env file is not found
    """
    try:
        # Load environment variables from .env file
        load_dotenv()
        logger.info("Loading environment configuration...")
        
        # Retrieve API keys from environment
        pinecone_api_key = os.environ.get('PINECONE_API_KEY')
        groq_api_key = os.environ.get('GROQ_API_KEY')
        
        # Validate that all required API keys are present
        if not pinecone_api_key:
            raise EnvironmentError("PINECONE_API_KEY not found in environment variables")
        if not groq_api_key:
            raise EnvironmentError("GROQ_API_KEY not found in environment variables")
        
        # Set environment variables for LangChain components
        os.environ['PINECONE_API_KEY'] = pinecone_api_key
        os.environ['GROQ_API_KEY'] = groq_api_key
        
        logger.info("Environment configuration loaded successfully")
        return pinecone_api_key, groq_api_key
        
    except FileNotFoundError:
        logger.error(".env file not found. Please create a .env file with API keys")
        raise
    except Exception as error:
        logger.error(f"Error loading environment configuration: {str(error)}")
        raise


def initialize_medical_embeddings() -> Optional[Any]:
    """
    Initialize the HuggingFace embeddings model for medical text processing.
    
    Creates and configures the embedding model used to convert medical text
    into vector representations for semantic similarity search in the vector database.
    
    Returns:
        Optional[Any]: Initialized embeddings model, or None if initialization fails
    
    Raises:
        Exception: If there are issues initializing the embedding model
    """
    try:
        logger.info("Initializing medical embeddings model...")
        embeddings_model = initialize_medical_embedding_model()
        logger.info("Medical embeddings model initialized successfully")
        return embeddings_model
        
    except Exception as error:
        logger.error(f"Failed to initialize medical embeddings: {str(error)}")
        return None


def setup_medical_vector_retriever(embeddings_model: Any, pinecone_api_key: str) -> Optional[Any]:
    """
    Set up the Pinecone vector database retriever for medical document search.
    
    This function connects to the Pinecone vector database containing medical
    documents and creates a retriever for finding relevant medical information
    based on semantic similarity to user queries.
    
    Args:
        embeddings_model (Any): The initialized embeddings model for vector conversion
        pinecone_api_key (str): API key for Pinecone vector database access
    
    Returns:
        Optional[Any]: Configured document retriever, or None if setup fails
    
    Raises:
        Exception: If there are connection or configuration issues with Pinecone
    """
    try:
        logger.info(f"Connecting to Pinecone vector database: {MEDICAL_VECTOR_INDEX_NAME}")
        
        # Connect to existing Pinecone index with medical documents
        medical_vector_store = PineconeVectorStore.from_existing_index(
            index_name=MEDICAL_VECTOR_INDEX_NAME, 
            embedding=embeddings_model
        )
        
        # Configure retriever with optimized settings for medical queries
        document_retriever = medical_vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": SIMILARITY_SEARCH_RESULTS_COUNT  # Number of relevant documents to retrieve
            }
        )
    
        
        return document_retriever
        
    except Exception as error:
        logger.error(f"Pinecone vector database connection failed: {str(error)}")
        logger.error("Please verify: Pinecone API key, index name, and vector database setup")
        return None


def initialize_medical_language_model(groq_api_key: str) -> Optional[ChatGroq]:
    """
    Initialize the Groq language model for medical response generation.
    
    Sets up the Groq API connection with the Meta Llama model optimized
    for medical question answering with accurate, deterministic responses.
    
    Args:
        groq_api_key (str): API key for Groq language model access
    
    Returns:
        Optional[ChatGroq]: Initialized language model, or None if setup fails
    
    Raises:
        Exception: If there are issues connecting to or configuring the Groq API
    """
    try:
        logger.info(f"Initializing Groq language model: {GROQ_MODEL_NAME}")
        
        # Initialize Groq ChatGroq model with medical-optimized settings
        language_model = ChatGroq(
            temperature=LLM_TEMPERATURE,  # Low temperature for consistent medical responses
            groq_api_key=groq_api_key,
            model_name=GROQ_MODEL_NAME,
            max_tokens=1024,  # Reasonable response length for medical queries
            timeout=30,  # Timeout for model responses
            max_retries=2  # Retry failed requests
        )
        return language_model
        
    except Exception as error:
        logger.error(f"Groq language model initialization failed: {str(error)}")
        logger.error("Please verify: Groq API key and internet connection")
        return None


def create_medical_rag_chain(language_model: ChatGroq, document_retriever: Any) -> Optional[Any]:
    """
    Create the Retrieval-Augmented Generation (RAG) chain for medical Q&A.
    
    This function combines the language model with the document retriever to create
    a RAG system that can answer medical questions using relevant context from
    the medical knowledge base.
    
    Args:
        language_model (ChatGroq): The initialized Groq language model
        document_retriever (Any): The configured Pinecone document retriever
    
    Returns:
        Optional[Any]: Configured RAG chain, or None if creation fails
    
    Raises:
        Exception: If there are issues creating the RAG chain components
    """
    try:
        logger.info("Creating medical RAG (Retrieval-Augmented Generation) chain...")
        
        # Create chat prompt template for medical Q&A with context
        medical_chat_prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),  # Medical system prompt from src.prompt
            ("human", "{input}")  # User's medical question
        ])
        
        # Create document processing chain for combining retrieved context
        document_combination_chain = create_stuff_documents_chain(
            llm=language_model,
            prompt=medical_chat_prompt
        )
        
        # Create complete RAG chain combining retrieval and generation
        rag_chain = create_retrieval_chain(
            retriever=document_retriever,
            combine_docs_chain=document_combination_chain
        )
        
        logger.info("Medical RAG chain created successfully")
        logger.info("Ready to provide context-aware medical responses")
        
        return rag_chain
        
    except Exception as error:
        logger.error(f"Failed to create medical RAG chain: {str(error)}")
        return None


def initialize_medical_chatbot_system() -> bool:
    """
    Initialize all components of the medical chatbot system.
    
    This function orchestrates the initialization of all required components:
    environment configuration, embeddings, vector database, language model,
    and RAG chain for the medical chatbot.
    
    Returns:
        bool: True if all components initialized successfully, False otherwise
    
    Raises:
        Exception: If there are critical initialization failures
    """
    global medical_embeddings_model, medical_document_retriever
    global medical_language_model, medical_rag_chain
    
    try:
        logger.info("Starting medical chatbot system initialization...")
        
        # Load environment configuration and API keys
        pinecone_key, groq_key = load_environment_configuration()
        
        # Initialize embeddings model
        medical_embeddings_model = initialize_medical_embeddings()
        if not medical_embeddings_model:
            logger.error("Cannot proceed without embeddings model")
            return False
        
        # Set up vector database retriever
        medical_document_retriever = setup_medical_vector_retriever(
            medical_embeddings_model, pinecone_key
        )
        if not medical_document_retriever:
            logger.error("Cannot proceed without document retriever")
            return False
        
        # Initialize language model
        medical_language_model = initialize_medical_language_model(groq_key)
        if not medical_language_model:
            logger.error("Cannot proceed without language model")
            return False
        
        # Create RAG chain
        medical_rag_chain = create_medical_rag_chain(
            medical_language_model, medical_document_retriever
        )
        if not medical_rag_chain:
            logger.error("Cannot proceed without RAG chain")
            return False
        
        logger.info("Medical chatbot system initialization completed successfully!")
        logger.info("Ready to serve medical AI assistance")
        
        return True
        
    except Exception as error:
        logger.error(f"Critical error during system initialization: {str(error)}")
        return False


# Flask route handlers
@medical_chatbot_app.route("/")
def serve_chat_interface():
    """
    Serve the main medical chatbot interface.
    
    Returns the HTML template for the medical chatbot web interface
    with modern styling and interactive features.
    
    Returns:
        str: Rendered HTML template for the chat interface
    
    Raises:
        500: If there are issues rendering the template
    """
    try:
        logger.info("Serving medical chatbot interface")
        return render_template('chat.html')
    except Exception as error:
        logger.error(f"Error serving chat interface: {str(error)}")
        abort(500)


@medical_chatbot_app.route("/get", methods=["POST"])
def process_medical_query():
    """
    Process medical questions and generate AI-powered responses.
    
    This endpoint receives medical questions from the chat interface,
    uses the RAG system to find relevant medical information, and
    generates contextually-aware responses using the language model.
    
    Expected POST data:
        msg (str): The user's medical question
    
    Returns:
        str: AI-generated medical response with relevant context
    
    Raises:
        400: If the request is malformed or missing required data
        503: If the medical AI system is unavailable
        500: If there are processing errors
    """
    try:
        # Validate request method and data
        if request.method != "POST":
            logger.warning("Invalid request method for medical query")
            abort(400)
        
        # Extract medical question from request
        if "msg" not in request.form:
            logger.warning("Missing medical question in request")
            abort(400)
        
        user_medical_question = request.form["msg"].strip()
        
        # Validate question content
        if not user_medical_question:
            return "Please provide a medical question for me to help you with."
        
        if len(user_medical_question) > 1000:
            return "Please keep your medical question under 1000 characters for better processing."
        
        logger.info(f"Processing medical query: {user_medical_question[:100]}...")
        
        # Check if medical AI system is available
        if (medical_rag_chain is None or 
            medical_document_retriever is None or 
            medical_language_model is None):
            
            logger.error("Medical AI system components unavailable")
            return ("Sorry, the medical AI assistant is currently unavailable. "
                   "Please try again later or consult with a healthcare professional.")
        
        # Process query through RAG system
        rag_response = medical_rag_chain.invoke({"input": user_medical_question})
        
        # Extract and validate response
        if "answer" not in rag_response:
            logger.error("Invalid response format from RAG system")
            return "I apologize, but I encountered an issue generating a response. Please try again."
        
        medical_ai_response = rag_response["answer"].strip()
        
        # Log successful response (truncated for privacy)
        logger.info(f" Generated medical response: {medical_ai_response[:100]}...")
        
        # Add medical disclaimer to response
        medical_disclaimer = ("\n\n Important: This information is for educational purposes only. "
                            "Always consult with a qualified healthcare professional for medical advice.")
        
        return medical_ai_response + medical_disclaimer
        
    except KeyError as error:
        logger.error(f" Missing required data in medical query request: {str(error)}")
        abort(400)
    except TimeoutError:
        logger.error("Timeout processing medical query")
        return ("The medical AI system is experiencing high load. "
                "Please try again in a moment.")
    except Exception as error:
        logger.error(f"Error processing medical query: {str(error)}")
        return ("I apologize, but I encountered an error processing your medical question. "
                "Please try again or consult with a healthcare professional.")


@medical_chatbot_app.route("/health")
def system_health_check():
    """
    Health check endpoint for monitoring system status.
    
    Returns information about the status of all medical chatbot components
    for monitoring and debugging purposes.
    
    Returns:
        dict: JSON response with system component status
    """
    try:
        health_status = {
            "status": "healthy",
            "components": {
                "embeddings_model": medical_embeddings_model is not None,
                "document_retriever": medical_document_retriever is not None,
                "language_model": medical_language_model is not None,
                "rag_chain": medical_rag_chain is not None
            },
            "ready_for_queries": all([
                medical_embeddings_model is not None,
                medical_document_retriever is not None,
                medical_language_model is not None,
                medical_rag_chain is not None
            ])
        }
        
        return jsonify(health_status)
    except Exception as error:
        logger.error(f"Error in health check: {str(error)}")
        return jsonify({"status": "error", "message": str(error)}), 500


def run_medical_chatbot_server():
    """
    Start the medical chatbot Flask server.
    
    Initializes the medical AI system and starts the Flask web server
    to serve the chatbot interface and API endpoints.
    
    Raises:
        SystemExit: If critical initialization fails
    """
    try:
        logger.info("Starting Medical AI Chatbot Server...")
        
        # Initialize medical chatbot system
        if not initialize_medical_chatbot_system():
            logger.error("Failed to initialize medical chatbot system")
            logger.error("Server startup aborted")
            raise SystemExit(1)
        
        # Start Flask development server
        logger.info(f"Starting Flask server on {FLASK_HOST}:{FLASK_PORT}")
        logger.info("Debug mode enabled (for development only)")
        logger.info("Available endpoints:")
        logger.info("/ - Medical chatbot interface")
        logger.info("  /get - Medical query processing API")
        logger.info("/health - System health check")
        
        medical_chatbot_app.run(
            host=FLASK_HOST,
            port=FLASK_PORT,
            debug=True, 
            threaded=True
        )
        
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as error:
        logger.error(f"Critical error starting server: {str(error)}")
        raise SystemExit(1)



if __name__ == '__main__':
    run_medical_chatbot_server()