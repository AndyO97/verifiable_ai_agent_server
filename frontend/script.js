const chatWindow = document.getElementById('chat-window');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat-btn');
const convStatus = document.getElementById('conv-status');
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const conversationList = document.getElementById('conversation-list');

let currentConversationId = null;

// --- Sidebar toggle ---

sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
});

// --- Conversation list ---

async function loadConversationList() {
  try {
    const res = await fetch('/api/conversations');
    const conversations = await res.json();
    renderConversationList(conversations);
  } catch (e) {
    console.error('Failed to load conversations:', e);
  }
}

function renderConversationList(conversations) {
  conversationList.innerHTML = '';

  if (!conversations || conversations.length === 0) {
    conversationList.innerHTML = '<div class="sidebar-empty">No conversations yet</div>';
    return;
  }

  conversations.forEach(conv => {
    const item = document.createElement('div');
    item.classList.add('conv-item');
    if (conv.conversation_id === currentConversationId) {
      item.classList.add('active');
    }

    const title = document.createElement('div');
    title.classList.add('conv-title');
    // Use first message preview or session_id snippet as title
    const displayId = conv.session_id || conv.conversation_id;
    title.textContent = displayId.length > 28 ? displayId.slice(0, 28) + '…' : displayId;

    const meta = document.createElement('div');
    meta.classList.add('conv-meta');

    // Date
    const dateStr = conv.created_at
      ? new Date(conv.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      : '';
    const dateSpan = document.createElement('span');
    dateSpan.textContent = dateStr;

    // Prompt count
    const countSpan = document.createElement('span');
    const promptCount = conv.prompt_count || 0;
    countSpan.textContent = `${promptCount} msg${promptCount !== 1 ? 's' : ''}`;

    // Status badge
    const badge = document.createElement('span');
    badge.classList.add('badge');
    if (conv.is_finalized) {
      badge.classList.add('finalized');
      badge.textContent = 'Finalized';
    } else {
      badge.classList.add('active-badge');
      badge.textContent = 'Active';
    }

    meta.appendChild(dateSpan);
    meta.appendChild(countSpan);
    meta.appendChild(badge);

    item.appendChild(title);
    item.appendChild(meta);

    item.addEventListener('click', () => switchToConversation(conv));
    conversationList.appendChild(item);
  });
}

async function switchToConversation(conv) {
  currentConversationId = conv.conversation_id;

  // Update sidebar active state
  document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
  // Find and highlight the clicked item
  const items = conversationList.querySelectorAll('.conv-item');
  items.forEach(el => {
    const titleEl = el.querySelector('.conv-title');
    const displayId = conv.session_id || conv.conversation_id;
    const expected = displayId.length > 28 ? displayId.slice(0, 28) + '…' : displayId;
    if (titleEl && titleEl.textContent === expected) {
      el.classList.add('active');
    }
  });

  updateStatus(conv.is_finalized ? 'Finalized (read-only)' : 'Session active');
  clearChat();

  // Load messages
  try {
    const res = await fetch(`/api/conversations/${conv.conversation_id}/messages`);
    const messages = await res.json();
    if (Array.isArray(messages)) {
      messages.forEach(msg => {
        const sender = msg.role === 'user' ? 'user' : 'agent';
        addMessage(msg.content, sender);
      });
    }
  } catch (e) {
    addMessage('Failed to load messages: ' + e, 'agent');
  }

  // Disable input for finalized conversations
  chatInput.disabled = !!conv.is_finalized;
  sendBtn.disabled = !!conv.is_finalized;
  if (conv.is_finalized) {
    chatInput.placeholder = 'This conversation is finalized';
  } else {
    chatInput.placeholder = 'Type your prompt...';
  }
}

// --- Conversation management ---

async function startConversation() {
  try {
    const res = await fetch('/api/conversations', { method: 'POST' });
    const data = await res.json();
    currentConversationId = data.conversation_id;
    updateStatus('Session active');
    chatInput.disabled = false;
    sendBtn.disabled = false;
    chatInput.placeholder = 'Type your prompt...';
    console.log('Conversation started:', currentConversationId);
    // Refresh sidebar
    await loadConversationList();
  } catch (e) {
    console.error('Failed to start conversation:', e);
    updateStatus('Fallback mode');
    currentConversationId = null;
  }
}

function updateStatus(text) {
  if (convStatus) {
    convStatus.textContent = text;
  }
}

function clearChat() {
  chatWindow.innerHTML = '';
}

function addMessage(text, sender) {
  const messageDiv = document.createElement('div');
  messageDiv.classList.add('message', sender);
  messageDiv.textContent = text;
  chatWindow.appendChild(messageDiv);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addTypingIndicator() {
  const typing = document.createElement('div');
  typing.classList.add('message', 'agent', 'typing');
  typing.id = 'typing-indicator';
  typing.textContent = 'Thinking...';
  chatWindow.appendChild(typing);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return typing;
}

function removeTypingIndicator() {
  const typing = document.getElementById('typing-indicator');
  if (typing) typing.remove();
}

// --- Send message ---

async function sendMessage(e) {
  e.preventDefault();
  const prompt = chatInput.value.trim();
  if (!prompt) return;

  addMessage(prompt, 'user');
  chatInput.value = '';
  sendBtn.disabled = true;

  const typing = addTypingIndicator();

  try {
    let url, body;

    if (currentConversationId) {
      url = `/api/conversations/${currentConversationId}/chat`;
      body = JSON.stringify({ prompt });
    } else {
      url = '/api/chat';
      body = JSON.stringify({ prompt });
    }

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
    });

    const data = await res.json();
    removeTypingIndicator();

    if (data.error) {
      addMessage('Error: ' + data.error, 'agent');
    } else {
      addMessage(data.response || '(No response)', 'agent');
      if (data.prompt_root) {
        updateStatus(`Prompt #${data.prompt_index} verified`);
      }
    }

    // Refresh sidebar to update message counts
    await loadConversationList();
  } catch (err) {
    removeTypingIndicator();
    addMessage('Error contacting backend: ' + err, 'agent');
  }

  sendBtn.disabled = false;
  chatInput.focus();
}

// --- New Chat ---

async function handleNewChat() {
  // Finalize current conversation if one exists
  if (currentConversationId) {
    try {
      await fetch(`/api/conversations/${currentConversationId}/finalize`, { method: 'POST' });
      console.log('Previous conversation finalized:', currentConversationId);
    } catch (e) {
      console.error('Failed to finalize conversation:', e);
    }
  }

  clearChat();
  await startConversation();
  addMessage('New conversation started. How can I help you?', 'agent');
}

// --- Event listeners ---

chatForm.addEventListener('submit', sendMessage);

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(e);
  }
});

if (newChatBtn) {
  newChatBtn.addEventListener('click', handleNewChat);
}

// --- Initialize ---

async function init() {
  await loadConversationList();
  await startConversation();
}

init();
