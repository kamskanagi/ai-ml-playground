import React, { useState, useEffect } from 'react';
import './App.css';
import FileUpload from './components/FileUpload';
import AudioRecorder from './components/AudioRecorder';
import TranscriptDisplay from './components/TranscriptDisplay';
import { transcribeAudio, cleanupTranscript, transcribeAndCleanup, checkHealth } from './services/api';

function App() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState('');
  const [originalTranscript, setOriginalTranscript] = useState('');
  const [cleanedTranscript, setCleanedTranscript] = useState('');
  const [error, setError] = useState('');
  const [apiStatus, setApiStatus] = useState('checking');
  const [mode, setMode] = useState('record-and-cleanup'); // 'record-and-cleanup', 'combined', 'transcribe-only', 'cleanup-only'

  useEffect(() => {
    checkApiHealth();
  }, []);

  const checkApiHealth = async () => {
    try {
      await checkHealth();
      setApiStatus('connected');
    } catch (err) {
      setApiStatus('disconnected');
    }
  };

  const handleFileSelect = (file) => {
    setSelectedFile(file);
    setError('');
    setOriginalTranscript('');
    setCleanedTranscript('');
  };

  const handleRecordingComplete = async (audioFile) => {
    setSelectedFile(audioFile);
    setError('');
    setOriginalTranscript('');
    setCleanedTranscript('');

    // Automatically start transcription after recording
    setIsProcessing(true);

    try {
      if (mode === 'record-and-cleanup') {
        setProcessingStep('Transcribing audio...');
        const result = await transcribeAndCleanup(audioFile);

        if (result.success) {
          setOriginalTranscript(result.original_transcript);
          setCleanedTranscript(result.cleaned_transcript);
          setProcessingStep('');
        } else {
          setError('Processing failed. Please try again.');
        }
      } else {
        // record-only mode
        setProcessingStep('Transcribing audio...');
        const result = await transcribeAudio(audioFile);

        if (result.success) {
          setOriginalTranscript(result.transcript);
          setProcessingStep('');
        } else {
          setError('Transcription failed. Please try again.');
        }
      }
    } catch (err) {
      console.error('Error:', err);
      setError(err.response?.data?.detail || 'An error occurred during processing. Please try again.');
      setProcessingStep('');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleTranscribeAndCleanup = async () => {
    if (!selectedFile) {
      setError('Please select a file first');
      return;
    }

    setIsProcessing(true);
    setError('');
    setOriginalTranscript('');
    setCleanedTranscript('');

    try {
      setProcessingStep('Transcribing audio...');
      const result = await transcribeAndCleanup(selectedFile);

      if (result.success) {
        setOriginalTranscript(result.original_transcript);
        setCleanedTranscript(result.cleaned_transcript);
        setProcessingStep('');
      } else {
        setError('Processing failed. Please try again.');
      }
    } catch (err) {
      console.error('Error:', err);
      setError(err.response?.data?.detail || 'An error occurred during processing. Please try again.');
      setProcessingStep('');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleTranscribeOnly = async () => {
    if (!selectedFile) {
      setError('Please select a file first');
      return;
    }

    setIsProcessing(true);
    setError('');
    setOriginalTranscript('');
    setCleanedTranscript('');

    try {
      setProcessingStep('Transcribing audio...');
      const result = await transcribeAudio(selectedFile);

      if (result.success) {
        setOriginalTranscript(result.transcript);
        setProcessingStep('');
      } else {
        setError('Transcription failed. Please try again.');
      }
    } catch (err) {
      console.error('Error:', err);
      setError(err.response?.data?.detail || 'An error occurred during transcription. Please try again.');
      setProcessingStep('');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCleanupOnly = async () => {
    if (!originalTranscript) {
      setError('Please transcribe an audio file first or paste a transcript');
      return;
    }

    setIsProcessing(true);
    setError('');
    setCleanedTranscript('');

    try {
      setProcessingStep('Cleaning up transcript...');
      const result = await cleanupTranscript(originalTranscript);

      if (result.success) {
        setCleanedTranscript(result.cleaned_transcript);
        setProcessingStep('');
      } else {
        setError('Cleanup failed. Please try again.');
      }
    } catch (err) {
      console.error('Error:', err);
      setError(err.response?.data?.detail || 'An error occurred during cleanup. Please try again.');
      setProcessingStep('');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleProcess = () => {
    if (mode === 'combined') {
      handleTranscribeAndCleanup();
    } else if (mode === 'transcribe-only') {
      handleTranscribeOnly();
    } else if (mode === 'cleanup-only') {
      handleCleanupOnly();
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Transcription Studio</h1>
        <p>Whisper AI + Local LLM Processing</p>
        <div className={`api-status ${apiStatus}`}>
          {apiStatus === 'connected' ? 'System Online' : apiStatus === 'checking' ? 'Connecting...' : 'System Offline'}
        </div>
      </header>

      <main className="App-main">
        <div className="controls-section">
          <div className="mode-selector">
            <label>
              <input
                type="radio"
                value="record-and-cleanup"
                checked={mode === 'record-and-cleanup'}
                onChange={(e) => setMode(e.target.value)}
                disabled={isProcessing}
              />
              Record
            </label>
            <label>
              <input
                type="radio"
                value="combined"
                checked={mode === 'combined'}
                onChange={(e) => setMode(e.target.value)}
                disabled={isProcessing}
              />
              Upload + Clean
            </label>
            <label>
              <input
                type="radio"
                value="transcribe-only"
                checked={mode === 'transcribe-only'}
                onChange={(e) => setMode(e.target.value)}
                disabled={isProcessing}
              />
              Transcribe
            </label>
            <label>
              <input
                type="radio"
                value="cleanup-only"
                checked={mode === 'cleanup-only'}
                onChange={(e) => setMode(e.target.value)}
                disabled={isProcessing}
              />
              Clean Text
            </label>
          </div>

          {mode === 'record-and-cleanup' && (
            <AudioRecorder onRecordingComplete={handleRecordingComplete} isProcessing={isProcessing} />
          )}

          {(mode === 'combined' || mode === 'transcribe-only') && (
            <FileUpload onFileSelect={handleFileSelect} isProcessing={isProcessing} />
          )}

          {mode === 'cleanup-only' && (
            <div className="manual-input">
              <label>Paste your transcript here:</label>
              <textarea
                value={originalTranscript}
                onChange={(e) => setOriginalTranscript(e.target.value)}
                placeholder="Paste your transcript here to clean it up..."
                rows="6"
                disabled={isProcessing}
              />
            </div>
          )}

          {mode !== 'record-and-cleanup' && (
            <button
              onClick={handleProcess}
              disabled={isProcessing || (mode !== 'cleanup-only' && !selectedFile) || (mode === 'cleanup-only' && !originalTranscript)}
              className="btn btn-primary"
            >
              {isProcessing ? processingStep :
                mode === 'combined' ? 'Transcribe & Cleanup' :
                mode === 'transcribe-only' ? 'Transcribe' :
                'Cleanup Transcript'}
            </button>
          )}

          {mode === 'record-and-cleanup' && isProcessing && (
            <div className="btn btn-primary" style={{ opacity: 0.6 }}>
              {processingStep}
            </div>
          )}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}
        </div>

        <div className="results-section">
          {originalTranscript && (
            <TranscriptDisplay
              transcript={originalTranscript}
              title="Original Transcript"
              onCopy={() => console.log('Copied original transcript')}
              onDownload={() => console.log('Downloaded original transcript')}
            />
          )}

          {cleanedTranscript && (
            <TranscriptDisplay
              transcript={cleanedTranscript}
              title="Cleaned Transcript"
              onCopy={() => console.log('Copied cleaned transcript')}
              onDownload={() => console.log('Downloaded cleaned transcript')}
            />
          )}
        </div>
      </main>

      <footer className="App-footer">
        <p>Powered by Whisper + Ollama</p>
      </footer>
    </div>
  );
}

export default App;
