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

// --- HTTP Security: Session + HMAC signing ---

let sessionToken = null;
let hmacKeyHex = null;
let cryptoKey = null;  // CryptoKey object for HMAC-SHA256

const SESSION_TOKEN_STORAGE_KEY = 'mcp_session_token';
const HMAC_KEY_STORAGE_KEY = 'mcp_hmac_key_hex';

async function importHmacKey(hexKey) {
  const keyBytes = hexToBytes(hexKey);
  return crypto.subtle.importKey(
    'raw', keyBytes, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
}

async function restoreSessionFromStorage() {
  const storedToken = localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
  const storedHmacKeyHex = localStorage.getItem(HMAC_KEY_STORAGE_KEY);

  if (!storedToken || !storedHmacKeyHex) {
    return false;
  }

  try {
    cryptoKey = await importHmacKey(storedHmacKeyHex);
    sessionToken = storedToken;
    hmacKeyHex = storedHmacKeyHex;
    return true;
  } catch (e) {
    console.warn('Stored session key invalid, creating new session:', e);
    clearStoredSession();
    return false;
  }
}

function persistSession() {
  if (!sessionToken || !hmacKeyHex) {
    return;
  }
  localStorage.setItem(SESSION_TOKEN_STORAGE_KEY, sessionToken);
  localStorage.setItem(HMAC_KEY_STORAGE_KEY, hmacKeyHex);
}

function clearStoredSession() {
  localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
  localStorage.removeItem(HMAC_KEY_STORAGE_KEY);
}

/**
 * Initialize an authenticated HTTP session with the server.
 * Receives session_token + hmac_key for signing subsequent requests.
 */
async function initSession() {
  try {
    if (!sessionToken || !cryptoKey) {
      const restored = await restoreSessionFromStorage();
      if (restored) {
        console.log('Restored secure session:', sessionToken.slice(0, 8) + '...');
        return;
      }
    }

    const res = await fetch('/api/session/init', { method: 'POST' });
    let data = await res.json();
    // Handle MCP-wrapped response (has .result field)
    if (data.result) {
      data = data.result;
    }
    sessionToken = data.session_token;
    hmacKeyHex = data.hmac_key;

    cryptoKey = await importHmacKey(hmacKeyHex);
    persistSession();

    console.log('Secure session initialized:', sessionToken.slice(0, 8) + '...');
  } catch (e) {
    console.error('Failed to initialize secure session:', e);
  }
}

/** Convert hex string to Uint8Array */
function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes;
}

/** Convert ArrayBuffer to hex string */
function bufferToHex(buffer) {
  return Array.from(new Uint8Array(buffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

/** Generate a cryptographically random nonce (32 hex chars) */
function generateNonce() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Compute HMAC-SHA256 signature for a request.
 * message = "{timestamp}|{nonce}|{method}|{path}|{body}"
 */
async function signRequest(timestamp, nonce, method, path, body) {
  const message = `${timestamp}|${nonce}|${method}|${path}|${body}`;
  const encoded = new TextEncoder().encode(message);
  const sig = await crypto.subtle.sign('HMAC', cryptoKey, encoded);
  return bufferToHex(sig);
}

/**
 * Wrapper for fetch() that automatically adds security headers and unwraps MCP responses.
 * All /api/ calls should go through this.
 * Automatically re-initializes the session on 401 and retries once.
 * 
 * Returns a response object with a json() method that unwraps MCP responses.
 */
async function secureFetch(url, options = {}) {
  if (!sessionToken || !cryptoKey) {
    await initSession();
    if (!sessionToken) {
      throw new Error('No secure session available');
    }
  }

  let res;
  try {
    res = await _signedFetch(url, options);
  } catch (err) {
    console.warn('Network error, re-initializing session and retrying once:', err);
    sessionToken = null;
    hmacKeyHex = null;
    cryptoKey = null;
    clearStoredSession();
    await initSession();
    if (!sessionToken) {
      throw err;
    }
    res = await _signedFetch(url, options);
  }

  // If session expired (e.g. server restarted), re-init and retry once
  if (res.status === 401) {
    console.warn('Session expired, re-initializing...');
    sessionToken = null;
    hmacKeyHex = null;
    cryptoKey = null;
    clearStoredSession();
    await initSession();
    if (!sessionToken) {
      throw new Error('Failed to re-initialize session');
    }
    res = await _signedFetch(url, options);
  }

  // Wrap response.json() to automatically unwrap MCP-wrapped responses
  const originalJson = res.json.bind(res);
  res.json = async function() {
    const data = await originalJson();
    // If response has .result field (MCP-wrapped), extract it
    if (data && typeof data === 'object' && 'result' in data) {
      return data.result;
    }
    return data;
  };

  return res;
}

/**
 * Internal: perform a single fetch with HMAC signing.
 */
async function _signedFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const body = options.body || '';
  const timestamp = Date.now().toString();
  const nonce = generateNonce();

  const path = new URL(url, window.location.origin).pathname;

  const signature = await signRequest(timestamp, nonce, method, path, body);

  const headers = {
    ...(options.headers || {}),
    'X-Session-Token': sessionToken,
    'X-Timestamp': timestamp,
    'X-Nonce': nonce,
    'X-Signature': signature,
  };

  return fetch(url, { ...options, headers });
}

// --- Sidebar toggle ---

sidebarToggle.addEventListener('click', () => {
  sidebar.classList.toggle('collapsed');
});

// --- Conversation list ---

async function loadConversationList() {
  try {
    const res = await secureFetch('/api/conversations');
    const conversations = await res.json();
    // Guard against non-array responses (e.g. error objects from backend)
    const conversationList = Array.isArray(conversations) ? conversations : [];
    renderConversationList(conversationList);
  } catch (e) {
    console.error('Failed to load conversations:', e);
  }
}

function renderConversationList(conversations) {
  conversationList.innerHTML = '';

  if (!Array.isArray(conversations) || conversations.length === 0) {
    conversationList.innerHTML = '<div class="sidebar-empty">No conversations yet</div>';
    return;
  }

  conversations.forEach(conv => {
    const item = document.createElement('div');
    item.classList.add('conv-item');
    if (conv.conversation_id === currentConversationId) {
      item.classList.add('active');
    }

    const topRow = document.createElement('div');
    topRow.classList.add('conv-top-row');

    const title = document.createElement('div');
    title.classList.add('conv-title');
    // Use first message preview or session_id snippet as title
    const displayId = conv.session_id || conv.conversation_id;
    title.textContent = displayId.length > 24 ? displayId.slice(0, 24) + '…' : displayId;

    const deleteBtn = document.createElement('button');
    deleteBtn.classList.add('conv-delete-btn');
    deleteBtn.title = 'Delete conversation';
    deleteBtn.innerHTML = '&#128465;';  // wastebasket icon
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();  // Don't trigger switchToConversation
      deleteConversation(conv.conversation_id);
    });

    topRow.appendChild(title);
    topRow.appendChild(deleteBtn);

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

    item.appendChild(topRow);
    item.appendChild(meta);

    item.addEventListener('click', () => switchToConversation(conv));
    conversationList.appendChild(item);
  });
}

async function deleteConversation(conversationId) {
  if (!confirm('Delete this conversation?\nThis will remove it from the database, workflow files, and Langfuse.')) {
    return;
  }

  try {
    const res = await secureFetch(`/api/conversations/${conversationId}`, {
      method: 'DELETE',
    });
    const data = await res.json();

    if (data.error) {
      alert('Delete failed: ' + data.error);
      return;
    }

    const wasActive = conversationId === currentConversationId;

    await loadConversationList();

    // If deleted conversation was active, auto-select the most recent remaining one
    if (wasActive) {
      const res = await secureFetch('/api/conversations');
      const convs = await res.json();
      
      if (convs && convs.length > 0) {
        // Auto-select the first (most recent) conversation
        const nextConv = convs[0];
        await switchToConversation(nextConv);
        addMessage('Previous conversation deleted. Switched to most recent.', 'agent');
      } else {
        // No conversations left
        currentConversationId = null;
        updateStatus('No conversations. Click "+ New" to create one.');
        clearChat();
        chatInput.disabled = true;
        sendBtn.disabled = true;
        chatInput.placeholder = 'Click "+ New" to create a conversation';
      }
    }
  } catch (e) {
    console.error('Failed to delete conversation:', e);
    alert('Error deleting conversation: ' + e);
  }
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
    const expected = displayId.length > 24 ? displayId.slice(0, 24) + '…' : displayId;
    if (titleEl && titleEl.textContent === expected) {
      el.classList.add('active');
    }
  });

  updateStatus(conv.is_finalized ? 'Finalized (read-only)' : 'Session active');
  clearChat();

  // Load messages
  try {
    const res = await secureFetch(`/api/conversations/${conv.conversation_id}/messages`);
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
    const res = await secureFetch('/api/conversations', { method: 'POST' });
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

  // Safeguard: prevent sending if no conversation selected
  if (!currentConversationId) {
    addMessage('Error: No conversation selected. Click a conversation or create a new one.', 'agent');
    return;
  }

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

    const res = await secureFetch(url, {
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
      const res = await secureFetch(`/api/conversations/${currentConversationId}/finalize`, { method: 'POST' });
      const data = await res.json();
      if (data.error) {
        console.warn('Finalize response:', data.error);
      } else {
        console.log('Previous conversation finalized:', currentConversationId);
      }
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
  await initSession();
  await loadConversationList();

  // Auto-select the most recent conversation, or prompt user to create one
  const res = await secureFetch('/api/conversations');
  const convs = await res.json();
  if (convs && convs.length > 0) {
    await switchToConversation(convs[0]);
  } else {
    chatInput.disabled = true;
    sendBtn.disabled = true;
    chatInput.placeholder = 'Click "+ New" to create a conversation';
    updateStatus('No conversations yet');
  }
}

init();
