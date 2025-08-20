// Get references to all the necessary DOM elements
const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendButton = document.getElementById('send-button');
const micButton = document.getElementById('mic-button');

// --- Configuration ---
const BACKEND_URL = 'http://127.0.0.1:8000';

// Global variables for the new recording workflow
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let isTyping = false;

// --- Message Display Functions ---

/**
 * Creates and displays a new message in the chat box.
 * @param {object} message - An object {text: string, audioUrl: string (optional)}.
 * @param {string} sender - The type of sender ('user' or 'system').
 */
function addMessage(message, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    messageDiv.classList.add(`${sender}-message`);

    // Add a paragraph for the message text
    const textParagraph = document.createElement('p');
    textParagraph.textContent = message.text;
    messageDiv.appendChild(textParagraph);

    // If there is audio data, add a play button
    if (message.audioUrl) {
        const audio = new Audio(message.audioUrl);
        const playButton = document.createElement('button');
        playButton.textContent = '▶️';
        playButton.classList.add('audio-play-button');
        playButton.title = 'Play audio response';

        // Add a click listener to play the audio
        playButton.onclick = () => {
            audio.play().catch(e => console.error("Error playing audio:", e));
        };
        
        messageDiv.appendChild(playButton);
    }
    
    chatBox.appendChild(messageDiv);
    // Automatically scroll to the bottom
    chatBox.scrollTop = chatBox.scrollHeight;
}

/**
 * Adds a "typing..." indicator to the chat box.
 */
function addTypingIndicator() {
    if (isTyping) return;
    isTyping = true;
    const typingIndicator = document.createElement('div');
    typingIndicator.id = 'typing-indicator';
    typingIndicator.classList.add('typing-indicator');
    typingIndicator.innerHTML = '<span></span><span></span><span></span>';
    chatBox.appendChild(typingIndicator);
    chatBox.scrollTop = chatBox.scrollHeight;
}

/**
 * Removes the "typing..." indicator from the chat box.
 */
function removeTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) {
        indicator.remove();
        isTyping = false;
    }
}

// --- Backend Communication ---

/**
 * Sends a message to the backend API.
 * @param {string} type - 'text' or 'audio'.
 * @param {string|Blob} content - The text string or the audio Blob.
 */
async function sendMessageToBackend(type, content) {
    const formData = new FormData();
    if (type === 'text') {
        formData.append('text_input', content);
        addMessage({ text: content, audioUrl: null }, 'user');
    } else if (type === 'audio') {
        formData.append('audio_file', content, 'audio_input.webm');
        addMessage({ text: "Audio message", audioUrl: URL.createObjectURL(content) }, 'user');
    }

    addTypingIndicator();

    try {
        const response = await fetch(`${BACKEND_URL}/chat`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Backend error: ${response.status} - ${errorData.detail || 'Unknown error'}`);
        }

        const data = await response.json();
        removeTypingIndicator();

        const responseText = data.response_text || "No text response.";
        const responseAudioBase64 = data.response_audio;

        let responseAudioUrl = null;
        if (responseAudioBase64) {
            responseAudioUrl = `data:audio/wav;base64,${responseAudioBase64}`;
        }

        addMessage({ text: responseText, audioUrl: responseAudioUrl }, 'system');

    } catch (error) {
        console.error('Error communicating with backend:', error);
        removeTypingIndicator();
        addMessage({ text: `Error: ${error.message}. Please check the backend server.`, audioUrl: null }, 'system');
    }
}

// --- Audio Recording Functions ---

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
        
        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            sendMessageToBackend('audio', audioBlob);
            audioChunks = [];
            isRecording = false;
            micButton.textContent = '🎤';
            micButton.classList.remove('recording');
        };

        mediaRecorder.start();
        isRecording = true;
        micButton.textContent = '🔴';
        micButton.classList.add('recording');
        console.log('Recording started.');

    } catch (error) {
        console.error('Microphone access denied or not available:', error);
        alert('Microphone access is required to use voice chat.');
    }
}

function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        console.log('Recording stopped.');
    }
}

// --- Event Listeners ---

// Handle the mic button for recording
micButton.addEventListener('click', () => {
    if (isRecording) {
        stopRecording();
    } else {
        startRecording();
    }
});

// Toggle the send and mic buttons based on text input
userInput.addEventListener('input', () => {
    if (userInput.value.trim().length > 0) {
        sendButton.style.display = 'inline-block';
        micButton.style.display = 'none';
    } else {
        sendButton.style.display = 'none';
        micButton.style.display = 'inline-block';
    }
});

// Handle sending a text message
sendButton.addEventListener('click', () => {
    const textMessage = userInput.value.trim();
    if (textMessage) {
        sendMessageToBackend('text', textMessage);
        userInput.value = '';
        sendButton.style.display = 'none';
        micButton.style.display = 'inline-block';
    }
});

// Handle Enter key for text messages
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        sendButton.click();
    }
});

// Initially hide the send button and show a welcome message
document.addEventListener('DOMContentLoaded', () => {
    sendButton.style.display = 'none';
    addMessage({ text: "Hello! How can I assist you with your banking queries today?", audioUrl: null }, 'system');
});