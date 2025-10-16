// Medical AI Chatbot JavaScript
class MedicalChatbot {
    constructor() {
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.chatMessages = document.getElementById('chatMessages');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.charCounter = document.getElementById('charCounter');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.infoPanel = document.getElementById('infoPanel');
        
        this.isProcessing = false;
        this.maxCharacters = 1000;
        
        this.initializeEventListeners();
        this.updateWelcomeTime();
        this.autoResizeTextarea();
    }
    
    initializeEventListeners() {
        // Send button click
        this.sendButton.addEventListener('click', () => this.sendMessage());
        
        // Enter key to send (Shift+Enter for new line)
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Character counter update
        this.messageInput.addEventListener('input', () => {
            this.updateCharCounter();
            this.autoResizeTextarea();
            this.updateSendButtonState();
        });
        
        // Auto-resize textarea
        this.messageInput.addEventListener('input', () => this.autoResizeTextarea());
    }
    
    updateWelcomeTime() {
        const welcomeTimeElement = document.getElementById('welcomeTime');
        if (welcomeTimeElement) {
            welcomeTimeElement.textContent = this.formatTime(new Date());
        }
    }
    
    updateCharCounter() {
        const currentLength = this.messageInput.value.length;
        this.charCounter.textContent = `${currentLength}/${this.maxCharacters}`;
        
        if (currentLength > this.maxCharacters * 0.9) {
            this.charCounter.classList.add('warning');
        } else {
            this.charCounter.classList.remove('warning');
        }
    }
    
    autoResizeTextarea() {
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
    }
    
    updateSendButtonState() {
        const hasText = this.messageInput.value.trim().length > 0;
        const withinLimit = this.messageInput.value.length <= this.maxCharacters;
        
        this.sendButton.disabled = !hasText || !withinLimit || this.isProcessing;
    }
    
    async sendMessage() {
        const message = this.messageInput.value.trim();
        
        if (!message || this.isProcessing) {
            return;
        }
        
        if (message.length > this.maxCharacters) {
            this.showError('Message is too long. Please keep it under 1000 characters.');
            return;
        }
        
        // Add user message to chat
        this.addMessage(message, 'user');
        
        // Clear input
        this.messageInput.value = '';
        this.updateCharCounter();
        this.autoResizeTextarea();
        this.updateSendButtonState();
        
        // Show processing state
        this.setProcessingState(true);
        
        try {
            // Send message to backend
            const response = await this.sendToBackend(message);
            
            // Hide typing indicator
            this.setProcessingState(false);
            
            // Add AI response to chat
            this.addMessage(response, 'ai');
            
        } catch (error) {
            console.error('Error sending message:', error);
            this.setProcessingState(false);
            
            let errorMessage = 'I apologize, but I encountered an error processing your question. ';
            
            if (error.message.includes('fetch')) {
                errorMessage += 'Please check your internet connection and try again.';
            } else if (error.message.includes('timeout')) {
                errorMessage += 'The request timed out. Please try again.';
            } else {
                errorMessage += 'Please try again or consult with a healthcare professional.';
            }
            
            this.addMessage(errorMessage, 'ai');
        }
    }
    
    async sendToBackend(message) {
        const formData = new FormData();
        formData.append('msg', message);
        
        const response = await fetch('/get', {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.text();
        return result;
    }
    
    setProcessingState(isProcessing) {
        this.isProcessing = isProcessing;
        
        if (isProcessing) {
            this.typingIndicator.classList.add('active');
            this.messageInput.disabled = true;
        } else {
            this.typingIndicator.classList.remove('active');
            this.messageInput.disabled = false;
            this.messageInput.focus();
        }
        
        this.updateSendButtonState();
        this.scrollToBottom();
    }
    
    addMessage(content, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        
        if (sender === 'ai') {
            avatarDiv.innerHTML = '<i class="fas fa-user-md"></i>';
        } else {
            avatarDiv.innerHTML = '<i class="fas fa-user"></i>';
        }
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const headerDiv = document.createElement('div');
        headerDiv.className = 'message-header';
        
        const senderName = document.createElement('span');
        senderName.className = 'sender-name';
        senderName.textContent = sender === 'ai' ? 'Medical AI Assistant' : 'You';
        
        const messageTime = document.createElement('span');
        messageTime.className = 'message-time';
        messageTime.textContent = this.formatTime(new Date());
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        
        // Format message content
        const formattedContent = this.formatMessageContent(content);
        textDiv.innerHTML = formattedContent;
        
        headerDiv.appendChild(senderName);
        headerDiv.appendChild(messageTime);
        
        contentDiv.appendChild(headerDiv);
        contentDiv.appendChild(textDiv);
        
        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }
    
    formatMessageContent(content) {
        // Convert line breaks to paragraphs
        const paragraphs = content.split('\n\n').filter(p => p.trim());
        
        return paragraphs.map(paragraph => {
            // Handle bold text (markdown-style)
            let formatted = paragraph.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            
            // Handle italic text
            formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
            
            // Handle line breaks within paragraphs
            formatted = formatted.replace(/\n/g, '<br>');
            
            return `<p>${formatted}</p>`;
        }).join('');
    }
    
    formatTime(date) {
        return date.toLocaleTimeString([], { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: true 
        });
    }
    
    scrollToBottom() {
        setTimeout(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }, 100);
    }
    
    showError(message) {
        // You can implement a toast notification or alert here
        alert(message);
    }
}

// Suggestion button functionality
function sendSuggestion(question) {
    const chatbot = window.medicalChatbot;
    if (chatbot && !chatbot.isProcessing) {
        chatbot.messageInput.value = question;
        chatbot.updateCharCounter();
        chatbot.autoResizeTextarea();
        chatbot.updateSendButtonState();
        chatbot.messageInput.focus();
    }
}

// Info panel toggle
function toggleInfo() {
    const infoPanel = document.getElementById('infoPanel');
    infoPanel.classList.toggle('active');
}

// Send message function (called from HTML)
function sendMessage() {
    if (window.medicalChatbot) {
        window.medicalChatbot.sendMessage();
    }
}

// Health check functionality
async function checkSystemHealth() {
    try {
        const response = await fetch('/health');
        const healthData = await response.json();
        
        console.log('System Health:', healthData);
        
        if (!healthData.ready_for_queries) {
            console.warn('System not fully initialized:', healthData.components);
        }
        
        return healthData;
    } catch (error) {
        console.error('Health check failed:', error);
        return null;
    }
}

// Error handling for network issues
window.addEventListener('online', () => {
    console.log('Connection restored');
    // You can add UI feedback here
});

window.addEventListener('offline', () => {
    console.log('Connection lost');
    // You can add UI feedback here
});

// Initialize chatbot when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.medicalChatbot = new MedicalChatbot();
    
    // Perform initial health check
    checkSystemHealth().then(health => {
        if (health && !health.ready_for_queries) {
            console.warn('Medical AI system is not fully ready');
        }
    });
    
    // Focus on input
    setTimeout(() => {
        if (window.medicalChatbot.messageInput) {
            window.medicalChatbot.messageInput.focus();
        }
    }, 500);
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K to focus on input
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        if (window.medicalChatbot && window.medicalChatbot.messageInput) {
            window.medicalChatbot.messageInput.focus();
        }
    }
    
    // Escape to close info panel
    if (e.key === 'Escape') {
        const infoPanel = document.getElementById('infoPanel');
        if (infoPanel && infoPanel.classList.contains('active')) {
            infoPanel.classList.remove('active');
        }
    }
});

// Prevent form submission on Enter in input field
document.addEventListener('submit', (e) => {
    e.preventDefault();
});

// Auto-save draft functionality (optional)
let draftTimer;
function saveDraft() {
    if (window.medicalChatbot && window.medicalChatbot.messageInput.value.trim()) {
        localStorage.setItem('medical_chat_draft', window.medicalChatbot.messageInput.value);
    } else {
        localStorage.removeItem('medical_chat_draft');
    }
}

function loadDraft() {
    const draft = localStorage.getItem('medical_chat_draft');
    if (draft && window.medicalChatbot) {
        window.medicalChatbot.messageInput.value = draft;
        window.medicalChatbot.updateCharCounter();
        window.medicalChatbot.autoResizeTextarea();
        window.medicalChatbot.updateSendButtonState();
    }
}

// Load draft on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(loadDraft, 100);
});

// Save draft periodically
document.addEventListener('input', (e) => {
    if (e.target.id === 'messageInput') {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(saveDraft, 1000);
    }
});

// Clear draft when message is sent
document.addEventListener('click', (e) => {
    if (e.target.id === 'sendButton') {
        localStorage.removeItem('medical_chat_draft');
    }
});