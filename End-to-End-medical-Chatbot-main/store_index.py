from src.helper import load_pdf_file, text_split, hugging_face_embedding_model
from langchain_pinecone import PineconeVectorStore
from pinecone import ServerlessSpec
from pinecone.grpc import PineconeGRPC as Pinecone
from dotenv import load_dotenv
import os

load_dotenv()
PINECONE_API_KEY = os.environ.get('PINECONE_API_KEY')
# OPENAI_KEY = os.environ.get('OPENAI_KEY')

extracted_data = load_pdf_file(data='Documents/')
text_chunks  = text_split(extracted_data)
embeddings = hugging_face_embedding_model()

pc = Pinecone(api_key=PINECONE_API_KEY)

index_name = "medicalchat"

pc.create_index(
        name=index_name,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region="us-east-1",

        )
    )

docsearch = PineconeVectorStore.from_documents(documents=text_chunks, index_name=index_name, embedding=embeddings)