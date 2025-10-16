"""
Simplified Medical AI Chatbot Flask Application

A basic version that works with Python 3.7 and available packages.
This version uses simpler dependencies and provides a functional medical chatbot interface.
"""

# Standard library imports
import os
import logging
from typing import Optional

# Third-party Flask imports
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)
app.config['SECRET_KEY'] = 'medical-ai-chatbot-secret-key'

# Application configuration
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 8081

# Load environment variables
load_dotenv()
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')

# Simple medical knowledge base (fallback when APIs are not available)
MEDICAL_KNOWLEDGE = {
    "diabetes": {
        "symptoms": "Common symptoms of diabetes include increased thirst, frequent urination, fatigue, blurred vision, and unexplained weight loss.",
        "treatment": "Diabetes treatment typically involves lifestyle changes, blood sugar monitoring, and may include medications or insulin therapy.",
        "prevention": "Diabetes prevention includes maintaining a healthy weight, regular exercise, and a balanced diet."
    },
    "hypertension": {
        "symptoms": "Hypertension often has no symptoms but may cause headaches, shortness of breath, or nosebleeds in severe cases.",
        "treatment": "Treatment includes lifestyle modifications like diet and exercise, and may require blood pressure medications.",
        "prevention": "Prevention involves limiting sodium intake, regular exercise, maintaining healthy weight, and limiting alcohol."
    },
    "heart disease": {
        "symptoms": "Symptoms may include chest pain, shortness of breath, fatigue, and irregular heartbeat.",
        "treatment": "Treatment varies but may include medications, lifestyle changes, and in some cases, surgical procedures.",
        "prevention": "Prevention includes a heart-healthy diet, regular exercise, not smoking, and managing stress."
    }
}

def get_medical_response(user_question: str) -> str:
    """
    Generate a medical response based on user question.
    This is a simplified version that uses basic keyword matching.
    """
    try:
        user_question_lower = user_question.lower()
        
        # Check for specific conditions
        for condition, info in MEDICAL_KNOWLEDGE.items():
            if condition in user_question_lower:
                if "symptom" in user_question_lower:
                    return f"Regarding {condition} symptoms: {info['symptoms']}"
                elif "treatment" in user_question_lower or "treat" in user_question_lower:
                    return f"Regarding {condition} treatment: {info['treatment']}"
                elif "prevention" in user_question_lower or "prevent" in user_question_lower:
                    return f"Regarding {condition} prevention: {info['prevention']}"
                else:
                    return f"About {condition}: {info['symptoms']} For treatment and prevention information, please consult with a healthcare professional."
        
        # General medical questions
        if any(word in user_question_lower for word in ["pain", "hurt", "ache"]):
            return "For pain management, it's important to identify the cause. Common approaches include rest, ice/heat therapy, and over-the-counter pain relievers. Please consult a healthcare professional for persistent or severe pain."
        
        if any(word in user_question_lower for word in ["fever", "temperature"]):
            return "Fever is often a sign that your body is fighting an infection. Stay hydrated, rest, and consider fever-reducing medications if needed. Seek medical attention if fever is high (over 103°F/39.4°C) or persistent."
        
        if any(word in user_question_lower for word in ["headache", "migraine"]):
            return "Headaches can have various causes including stress, dehydration, or underlying conditions. Stay hydrated, rest in a dark room, and consider over-the-counter pain relief. Consult a doctor for frequent or severe headaches."
        
        # Default response
        return "I understand you have a medical question. While I can provide general health information, it's important to consult with a qualified healthcare professional for personalized medical advice, diagnosis, and treatment recommendations."
        
    except Exception as e:
        logger.error(f"Error generating medical response: {str(e)}")
        return "I apologize, but I encountered an error processing your medical question. Please try again or consult with a healthcare professional."

@app.route("/")
def serve_chat_interface():
    """Serve the main medical chatbot interface."""
    try:
        logger.info("Serving medical chatbot interface")
        return render_template('chat.html')
    except Exception as error:
        logger.error(f"Error serving chat interface: {str(error)}")
        return "Error loading chat interface", 500

@app.route("/get", methods=["POST"])
def process_medical_query():
    """Process medical questions and generate responses."""
    try:
        # Validate request method and data
        if request.method != "POST":
            logger.warning("Invalid request method for medical query")
            return "Invalid request method", 400
        
        # Extract medical question from request
        if "msg" not in request.form:
            logger.warning("Missing medical question in request")
            return "Missing medical question", 400
        
        user_medical_question = request.form["msg"].strip()
        
        # Validate question content
        if not user_medical_question:
            return "Please provide a medical question for me to help you with."
        
        if len(user_medical_question) > 1000:
            return "Please keep your medical question under 1000 characters for better processing."
        
        logger.info(f"Processing medical query: {user_medical_question[:100]}...")
        
        # Generate response using simple knowledge base
        medical_ai_response = get_medical_response(user_medical_question)
        
        # Add medical disclaimer to response
        medical_disclaimer = ("\n\nImportant: This information is for educational purposes only. "
                            "Always consult with a qualified healthcare professional for medical advice.")
        
        return medical_ai_response + medical_disclaimer
        
    except Exception as error:
        logger.error(f"Error processing medical query: {str(error)}")
        return ("I apologize, but I encountered an error processing your medical question. "
                "Please try again or consult with a healthcare professional.")

@app.route("/health")
def system_health_check():
    """Health check endpoint for monitoring system status."""
    try:
        health_status = {
            "status": "healthy",
            "components": {
                "flask_app": True,
                "medical_knowledge_base": True,
                "groq_api": GROQ_API_KEY is not None,
                "pinecone_api": PINECONE_API_KEY is not None
            },
            "ready_for_queries": True,
            "note": "Using simplified medical knowledge base"
        }
        
        return jsonify(health_status)
    except Exception as error:
        logger.error(f"Error in health check: {str(error)}")
        return jsonify({"status": "error", "message": str(error)}), 500

def run_medical_chatbot_server():
    """Start the medical chatbot Flask server."""
    try:
        logger.info("Starting Simplified Medical AI Chatbot Server...")
        logger.info("Note: Using basic medical knowledge base")
        
        # Start Flask development server
        logger.info(f"Starting Flask server on {FLASK_HOST}:{FLASK_PORT}")
        logger.info("Available endpoints:")
        logger.info("/ - Medical chatbot interface")
        logger.info("/get - Medical query processing API")
        logger.info("/health - System health check")
        
        app.run(
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