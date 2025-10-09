import React, { useState, useRef } from 'react';
import './App.css';

function App() {
  const [selectedImage, setSelectedImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const fileInputRef = useRef(null);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files && files[0]) {
      handleFile(files[0]);
    }
  };

  const handleFileInput = (e) => {
    const files = e.target.files;
    if (files && files[0]) {
      handleFile(files[0]);
    }
  };

  const handleFile = (file) => {
    if (file && file.type.startsWith('image/')) {
      setSelectedImage(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result);
      };
      reader.readAsDataURL(file);
      setPrediction(null);
    }
  };

  const handlePrediction = async () => {
    if (!selectedImage) return;

    setIsLoading(true);
    const formData = new FormData();
    formData.append('file', selectedImage);

    try {
      const response = await fetch('http://localhost:8000/predict', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      setPrediction(data);
    } catch (error) {
      console.error('Error making prediction:', error);
      setPrediction({ error: 'Failed to make prediction. Please try again.' });
    } finally {
      setIsLoading(false);
    }
  };

  const handleReset = () => {
    setSelectedImage(null);
    setPreview(null);
    setPrediction(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="App">
      <div className="container">
        <div className="header-section">
          <h1 className="title">Potato Disease Classification</h1>
          <p className="subtitle">AI-Powered Plant Disease Detection System</p>

          <div className="intro-section">
            <p className="intro-text">
              Welcome to our advanced potato disease classification system. This application uses
              deep learning technology to identify common potato leaf diseases with high accuracy.
            </p>
            <div className="features">
              <div className="feature-item">
                <div className="feature-icon">🔍</div>
                <div className="feature-content">
                  <h3>Accurate Detection</h3>
                  <p>Identifies Early Blight, Late Blight, and Healthy leaves</p>
                </div>
              </div>
              <div className="feature-item">
                <div className="feature-icon">⚡</div>
                <div className="feature-content">
                  <h3>Instant Results</h3>
                  <p>Get predictions in seconds with confidence scores</p>
                </div>
              </div>
              <div className="feature-item">
                <div className="feature-icon">📱</div>
                <div className="feature-content">
                  <h3>Easy to Use</h3>
                  <p>Simply drag and drop or click to upload an image</p>
                </div>
              </div>
            </div>
            <p className="how-to">
              <strong>How to use:</strong> Upload a clear image of a potato leaf, and our AI model
              will analyze it to detect any diseases and provide a confidence score for the prediction.
            </p>
          </div>
        </div>

        <div
          className={`dropzone ${isDragging ? 'dragging' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileInput}
            style={{ display: 'none' }}
          />

          {!preview ? (
            <div className="dropzone-content">
              <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="dropzone-text">Drag and drop an image here</p>
              <p className="dropzone-subtext">or click to select a file</p>
            </div>
          ) : (
            <div className="preview-container">
              <img src={preview} alt="Preview" className="preview-image" />
            </div>
          )}
        </div>

        {preview && (
          <div className="button-group">
            <button
              className="btn btn-primary"
              onClick={handlePrediction}
              disabled={isLoading}
            >
              {isLoading ? 'Analyzing...' : 'Make Prediction'}
            </button>
            <button className="btn btn-secondary" onClick={handleReset}>
              Reset
            </button>
          </div>
        )}

        {prediction && !prediction.error && (
          <div className="prediction-result">
            <h2 className="result-title">Prediction Results</h2>
            <div className="result-card">
              <div className="result-item">
                <span className="result-label">Class:</span>
                <span className="result-value">{prediction.class}</span>
              </div>
              <div className="result-item">
                <span className="result-label">Confidence:</span>
                <span className="result-value">{(prediction.confidence * 100).toFixed(2)}%</span>
              </div>
            </div>
            <div className="confidence-bar">
              <div
                className="confidence-fill"
                style={{ width: `${prediction.confidence * 100}%` }}
              ></div>
            </div>
          </div>
        )}

        {prediction && prediction.error && (
          <div className="error-message">
            <p>{prediction.error}</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
