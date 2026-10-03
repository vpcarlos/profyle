(function() {
    // --- Header Logic ---
    const header = document.createElement('div');
    header.innerText = 'Profyle Trace View';
    header.className = 'profyle-header';
    
    // --- Chat Logic ---
    
    // Chat FAB
    const chatFab = document.createElement('button');
    chatFab.className = 'profyle-chat-fab';
    chatFab.innerHTML = '💬';
    chatFab.title = "Chat with AI Agent";
    
    // Chat Window
    const chatWindow = document.createElement('div');
    chatWindow.className = 'profyle-chat-window';
    chatWindow.style.display = 'none';
    
    chatWindow.innerHTML = `
        <div class="profyle-chat-header">
            <span>Profyle AI Agent</span>
            <span style="cursor:pointer;" id="profyle-chat-close">✖</span>
        </div>
        <div class="profyle-chat-body" id="profyle-chat-body">
            <div class="profyle-message profyle-message-agent">
                Hi! Ask me why this request is slow, or how to make it faster.
            </div>
        </div>
        <div class="profyle-chat-input-area">
            <input type="text" class="profyle-chat-input" id="profyle-chat-input" placeholder="Type a message...">
            <button class="profyle-chat-send" id="profyle-chat-send">Send</button>
        </div>
    `;

    // Event Listeners
    chatFab.addEventListener('click', () => {
        if (chatWindow.style.display === 'none') {
            chatWindow.style.display = 'flex';
        } else {
            chatWindow.style.display = 'none';
        }
    });

    chatWindow.querySelector('#profyle-chat-close').addEventListener('click', () => {
        chatWindow.style.display = 'none';
    });

    const chatBody = chatWindow.querySelector('#profyle-chat-body');
    const chatInput = chatWindow.querySelector('#profyle-chat-input');
    const chatSend = chatWindow.querySelector('#profyle-chat-send');

    // Conversation history sent to the server on every turn (the API is stateless).
    const history = [];

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        addMessage(text, 'user');
        history.push({ role: 'user', content: text });
        chatInput.value = '';
        chatSend.disabled = true;

        const loadingId = addMessage('Analyzing trace...', 'agent', true);

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ messages: history })
            });
            const data = await response.json();
            removeMessage(loadingId);

            if (!response.ok) {
                // Drop the unanswered turn so the history stays user/assistant alternating.
                history.pop();
                addMessage('Error: ' + (data.detail || response.statusText), 'agent');
                return;
            }
            history.push({ role: 'assistant', content: data.response });
            addMessage(data.response, 'agent');
        } catch (e) {
            history.pop();
            removeMessage(loadingId);
            addMessage('Error communicating with server: ' + e.message, 'agent');
        } finally {
            chatSend.disabled = false;
        }
    }

    chatSend.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    function addMessage(text, type, isLoading = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `profyle-message profyle-message-${type} ${isLoading ? 'loading' : ''}`;
        msgDiv.innerText = text;
        const id = 'msg-' + Date.now() + '-' + Math.random().toString(36).slice(2);
        msgDiv.id = id;
        chatBody.appendChild(msgDiv);
        chatBody.scrollTop = chatBody.scrollHeight;
        return id;
    }

    function removeMessage(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    // --- DOM Injection Logic ---

    function ensureElements() {
        if (document.body) {
            if (!document.body.contains(header)) {
                document.body.appendChild(header);
            }
            if (!document.body.contains(chatFab)) {
                document.body.appendChild(chatFab);
            }
            if (!document.body.contains(chatWindow)) {
                document.body.appendChild(chatWindow);
            }
        }
    }

    const observer = new MutationObserver((mutations) => {
        ensureElements();
    });

    observer.observe(document, { childList: true, subtree: true });
    
    // Initial attempt
    if (document.body) ensureElements();
    else document.addEventListener('DOMContentLoaded', ensureElements);
})();
