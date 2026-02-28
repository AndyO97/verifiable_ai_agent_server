const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');

const messages = [];

function addMessage(text, sender) {
  const messageDiv = document.createElement('div');
  messageDiv.classList.add('message', sender);
  messageDiv.textContent = text;
  chatWindow.appendChild(messageDiv);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}


chatForm.addEventListener('submit', async function(e) {
  e.preventDefault();
  const prompt = chatInput.value.trim();
  if (!prompt) return;
  addMessage(prompt, 'user');
  messages.push({ sender: 'user', text: prompt });
  chatInput.value = '';

  // Send prompt to backend
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ prompt })
    });
    const data = await response.json();
    addMessage(data.response || '(No response)', 'agent');
    messages.push({ sender: 'agent', text: data.response });
  } catch (err) {
    addMessage('Error contacting backend: ' + err, 'agent');
    messages.push({ sender: 'agent', text: 'Error: ' + err });
  }
});
