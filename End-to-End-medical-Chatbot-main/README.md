# End-to-End Medical Chatbot

A sophisticated medical AI chatbot powered by Retrieval-Augmented Generation (RAG) technology that provides intelligent medical information and assistance. The system combines advanced language models with a comprehensive medical knowledge base to deliver accurate, contextual responses with built-in safety features.


## 🌟 Features

### 🧠 **Advanced AI Architecture**
- **RAG-Powered Responses**: Uses Retrieval-Augmented Generation for accurate, context-aware medical answers
- **Vector Database Integration**: Pinecone vector database for efficient medical document retrieval
- **Multi-Model Support**: Groq (Meta Llama) and OpenAI language models
- **Semantic Search**: HuggingFace embeddings for intelligent document matching

### 🏥 **Medical-Specific Features**
- **Safety-First Design**: Automatic medical disclaimers and emergency warnings
- **Professional Interface**: Medical-themed, responsive chat interface
- **Knowledge Base**: Built-in medical information for common conditions
- **Fallback System**: Simple knowledge base when APIs are unavailable

### 🔧 **Technical Features**
- **Real-time Chat**: Modern web interface with typing indicators
- **Health Monitoring**: Built-in system health check endpoints
- **Document Processing**: PDF medical literature processing pipeline
- **Error Handling**: Comprehensive error handling and logging


## Getting Started

### Prerequisites

- Python 3.8 or higher
- Git

### Installation

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd End-to-End-medical-Chatbot
   ```

2. **Create a virtual environment**

   Using Conda:

   ```bash
   conda create -n medicalbot python=3.8 -y
   conda activate medicalbot
   ```

   Or using Python venv:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   Create a `.env` file in the project root:

   ```env
   # Required API Keys
   PINECONE_API_KEY=your_pinecone_api_key_here
   GROQ_API_KEY=your_groq_api_key_here
   
   # Optional
   OPENAI_API_KEY=your_openai_api_key_here  # Alternative to Groq
   ```

   > 📝 **Getting API Keys:**
   > - **Pinecone**: Sign up at [pinecone.io](https://pinecone.io)
   > - **Groq**: Get free API key at [console.groq.com](https://console.groq.com)

5. **Initialize vector database** (First time only)

   ```bash
   python store_index.py
   ```

   This will:
   - Create a Pinecone index named "medicalchat"
   - Process PDF documents from `Documents/` folder
   - Generate and store embeddings
  
## Usage

Run the application:

```bash
python app.py
```
The application will be available at: `http://127.0.0.1:8081`
