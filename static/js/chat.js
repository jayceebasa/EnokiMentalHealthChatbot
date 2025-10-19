// Wire the chat UI to /api/chat/ and /api/chat/context/ so you can test without reloading
let consentStatus = null;
let selectedConsent = null;

document.addEventListener("DOMContentLoaded", function () {
  const messageForm = document.querySelector(".message-form");
  const messageInput = document.querySelector(".message-input");
  const sendBtn = document.querySelector(".send-btn");
  const chatMessages = document.getElementById("chat-messages");
  const toneSelect = document.getElementById("tone");
  const languageSelect = document.getElementById("language"); // Hidden field for backend compatibility

  // Mobile menu elements
  const hamburgerBtn = document.getElementById("hamburger-btn");
  const mobileMenu = document.getElementById("mobile-menu");
  const mobileMenuOverlay = document.getElementById("mobile-menu-overlay");
  const mobileNewChat = document.getElementById("mobile-new-chat");
  const mobileConsent = document.getElementById("mobile-consent");
  const mobileHistory = document.getElementById("mobile-history");
  const mobileSettings = document.getElementById("mobile-settings");

  // Settings panel elements
  const settingsToggle = document.getElementById("settings-toggle");
  const settingsPanel = document.getElementById("settings-panel");
  const settingsOverlay = document.getElementById("settings-overlay");
  const closeSettings = document.getElementById("close-settings");

  // History panel elements
  const historyToggle = document.getElementById("history-toggle");
  const historyPanel = document.getElementById("history-panel");
  const historyOverlay = document.getElementById("history-overlay");
  const closeHistory = document.getElementById("close-history");
  const chatSessionsList = document.getElementById("chat-sessions-list");

  // New chat button
  const newChatBtn = document.getElementById("new-chat-btn");
  const refreshBtn = document.getElementById("refresh-btn"); // May not exist

  // Context elements (may not exist if context panel was removed)
  const summaryEl = document.getElementById("summary");
  const memoryEl = document.getElementById("memory");

  // Mobile menu toggle
  function toggleMobileMenu() {
    mobileMenu.classList.toggle("open");
    mobileMenuOverlay.classList.toggle("open");
    document.body.style.overflow = mobileMenu.classList.contains("open") ? "hidden" : "";
  }

  function closeMobileMenu() {
    mobileMenu.classList.remove("open");
    mobileMenuOverlay.classList.remove("open");
    document.body.style.overflow = "";
  }

  if (hamburgerBtn) {
    hamburgerBtn.addEventListener("click", toggleMobileMenu);
  }

  if (mobileMenuOverlay) {
    mobileMenuOverlay.addEventListener("click", closeMobileMenu);
  }

  // Mobile menu item handlers
  if (mobileNewChat) {
    mobileNewChat.addEventListener("click", function () {
      closeMobileMenu();
      if (newChatBtn) newChatBtn.click();
    });
  }

  if (mobileConsent) {
    mobileConsent.addEventListener("click", function () {
      closeMobileMenu();
      openConsentModal();
    });
  }

  if (mobileHistory) {
    mobileHistory.addEventListener("click", function () {
      closeMobileMenu();
      openHistory();
    });
  }

  if (mobileSettings) {
    mobileSettings.addEventListener("click", function () {
      closeMobileMenu();
      openSettings();
    });
  }

  // Consent elements
  const consentModal = document.getElementById("consent-modal");
  const consentOverlay = document.getElementById("consent-overlay");
  const consentOptions = document.querySelectorAll(".consent-option");
  const confirmConsentBtn = document.getElementById("confirm-consent");
  const cancelConsentBtn = document.getElementById("cancel-consent");
  const consentStatusElement = document.getElementById("consent-status");
  const ephemeralWarning = document.getElementById("ephemeral-warning");
  const enableStorageBtn = document.getElementById("enable-storage-btn");

  // Validate required elements
  if (!messageInput || !sendBtn || !chatMessages) {
    console.error("Required chat elements not found:", {
      messageInput: !!messageInput,
      sendBtn: !!sendBtn,
      chatMessages: !!chatMessages,
    });
    return;
  }

  // Rate limiting variables
  let lastMessageTime = 0;
  const RATE_LIMIT_MS = 5000; // 5 seconds
  let countdownInterval = null;

  // Global function for inline handlers
  window.handleSendMessage = function () {
    const message = messageInput.value.trim();
    if (message && !sendBtn.disabled) {
      sendMessage(message);
    }
  };

  function startCooldownTimer() {
    const now = Date.now();
    const timeSinceLastMessage = now - lastMessageTime;
    const remainingTime = RATE_LIMIT_MS - timeSinceLastMessage;

    if (remainingTime > 0) {
      sendBtn.disabled = true;
      let secondsLeft = Math.ceil(remainingTime / 1000);
      sendBtn.textContent = `Wait ${secondsLeft}s`;

      // Clear any existing interval
      if (countdownInterval) {
        clearInterval(countdownInterval);
      }

      // Update countdown every second
      countdownInterval = setInterval(() => {
        secondsLeft--;
        if (secondsLeft > 0) {
          sendBtn.textContent = `Wait ${secondsLeft}s`;
        } else {
          sendBtn.textContent = "Send";
          sendBtn.disabled = false;
          clearInterval(countdownInterval);
          countdownInterval = null;
        }
      }, 1000);
    } else {
      // No cooldown needed, enable button immediately
      sendBtn.textContent = "Send";
      sendBtn.disabled = false;
      if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
      }
    }
  }

  function scrollToBottom() {
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
  }

  function openSettings() {
    if (settingsPanel && settingsOverlay) {
      settingsPanel.classList.add("open");
      settingsOverlay.classList.add("open");
      document.body.style.overflow = "hidden";
    }
  }

  function closeSettingsPanel() {
    if (settingsPanel && settingsOverlay) {
      settingsPanel.classList.remove("open");
      settingsOverlay.classList.remove("open");
      document.body.style.overflow = "";
    }
  }

  function openHistory() {
    if (historyPanel && historyOverlay) {
      historyPanel.classList.add("open");
      historyOverlay.classList.add("open");
      document.body.style.overflow = "hidden";
      loadChatHistory();
    }
  }

  function closeHistoryPanel() {
    if (historyPanel && historyOverlay) {
      historyPanel.classList.remove("open");
      historyOverlay.classList.remove("open");
      document.body.style.overflow = "";
    }
  }

  function openConsentModal() {
    showConsentModal();
  }

  // Settings panel handlers
  if (settingsToggle) settingsToggle.addEventListener("click", openSettings);
  if (closeSettings) closeSettings.addEventListener("click", closeSettingsPanel);
  if (settingsOverlay) settingsOverlay.addEventListener("click", closeSettingsPanel);

  // History panel handlers
  if (historyToggle) historyToggle.addEventListener("click", openHistory);
  if (closeHistory) closeHistory.addEventListener("click", closeHistoryPanel);
  if (historyOverlay) historyOverlay.addEventListener("click", closeHistoryPanel);

  // Consent modal handlers
  if (consentStatusElement) {
    consentStatusElement.addEventListener("click", showConsentModal);
  }

  if (cancelConsentBtn) {
    cancelConsentBtn.addEventListener("click", hideConsentModal);
  }

  if (consentOverlay) {
    consentOverlay.addEventListener("click", hideConsentModal);
  }

  // Consent option selection
  consentOptions.forEach((option) => {
    option.addEventListener("click", function () {
      const wantsSecureMode = this.dataset.consent === "true";

      // Check if user is authenticated when trying to enable secure mode
      const isAuthenticated = window.isAuthenticated || false;

      if (wantsSecureMode && !isAuthenticated) {
        // Anonymous user trying to enable secure mode - redirect to login
        hideConsentModal();
        if (confirm("Secure storage requires an account. Would you like to create an account or log in now?")) {
          window.location.href = "/login/";
        }
        return;
      }

      // Allow selection
      selectedConsent = wantsSecureMode;
      updateConsentSelection();
    });
  });

  // Confirm consent button
  if (confirmConsentBtn) {
    confirmConsentBtn.addEventListener("click", function () {
      if (selectedConsent !== null) {
        updateConsent(selectedConsent);
      }
    });
  }

  // Enable storage button in ephemeral warning
  if (enableStorageBtn) {
    enableStorageBtn.addEventListener("click", function () {
      // Check if user is authenticated
      const isAuthenticated = window.isAuthenticated || false;

      if (!isAuthenticated) {
        // Anonymous user - redirect to login
        if (confirm("You need to create an account or log in to enable data storage. Would you like to go to the login page now?")) {
          window.location.href = "/login/";
        }
      } else {
        // Authenticated user - show consent modal
        showConsentModal();
      }
    });
  }

  // Auto-resize textarea
  if (messageInput) {
    messageInput.addEventListener("input", function () {
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 120) + "px";
    });
  }

  function fmtTime(d = new Date()) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function appendMessage({ sender, text, timeStr = null }) {
    // Only clear intro message when user sends their first message
    if (sender === "user") {
      clearIntroMessage();
    }
    const isUser = sender === "user";
    const wrapper = document.createElement("div");
    wrapper.className = `chat-message ${isUser ? "user-chat" : "bot-chat"}`;
    const content = document.createElement("div");
    content.className = "message-content";
    content.innerHTML = `
            <div class="sender-name">${isUser ? "User" : "EnokiAI"}</div>
            <div class="message-text"></div>
            <div class="message-time">${timeStr || fmtTime()}</div>
        `;
    // Convert newlines to <br> tags and set innerHTML with escaped HTML
    const escapedText = escapeHtml(text).replace(/\n/g, "<br>");
    content.querySelector(".message-text").innerHTML = escapedText;
    wrapper.appendChild(content);
    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  function showThinkingIndicator() {
    const wrapper = document.createElement("div");
    wrapper.className = "thinking-indicator";
    wrapper.id = "thinking-indicator";
    wrapper.innerHTML = `
            <div class="thinking-content">
                <div class="sender-name" style="font-size: 0.8rem; font-weight: 600; margin-bottom: 0; opacity: 0.8;">EnokiAI</div>
                <div class="thinking-dots">
                    <div class="thinking-dot"></div>
                    <div class="thinking-dot"></div>
                    <div class="thinking-dot"></div>
                </div>
                <span style="font-size: 0.9rem; color: #718096;">is thinking...</span>
            </div>
        `;
    chatMessages.appendChild(wrapper);
    scrollToBottom();
  }

  function hideThinkingIndicator() {
    const indicator = document.getElementById("thinking-indicator");
    if (indicator) {
      indicator.remove();
    }
  }

  function renderMemory(memory) {
    if (!memory || typeof memory !== "object") return "<em>No memory yet.</em>";
    const parts = [];
    if (memory.stressor) {
      parts.push(`<div class="row"><span class="key">Stressor:</span><span>${escapeHtml(memory.stressor)}</span></div>`);
    }
    if (memory.motivation) {
      parts.push(`<div class="row"><span class="key">Motivation:</span><span>${escapeHtml(memory.motivation)}</span></div>`);
    }
    if (Array.isArray(memory.coping) && memory.coping.length) {
      parts.push(
        `<div class="row"><span class="key">Coping:</span>${memory.coping.map((c) => `<span class="pill">${escapeHtml(String(c))}</span>`).join("")}</div>`
      );
    }
    if (memory.trajectory) {
      parts.push(`<div class="row"><span class="key">Trajectory:</span><span>${escapeHtml(memory.trajectory)}</span></div>`);
    }
    if (Array.isArray(memory.bot_openings) && memory.bot_openings.length) {
      parts.push(
        `<div class="row"><span class="key">Recent openings:</span>${memory.bot_openings
          .slice(-5)
          .map((c) => `<span class="pill">${escapeHtml(String(c))}</span>`)
          .join("")}</div>`
      );
    }
    return parts.length ? parts.join("") : "<em>No memory yet.</em>";
  }

  function escapeHtml(str) {
    return String(str).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  }

  async function fetchContext() {
    try {
      const res = await fetch("/api/chat/context/", { credentials: "same-origin" });
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      // Update context panel
      if (summaryEl) summaryEl.textContent = data.summary || "";
      if (memoryEl) memoryEl.innerHTML = renderMemory(data.memory);

      // Load ephemeral chat history if available (no consent mode)
      if (data.ephemeral_history && Array.isArray(data.ephemeral_history) && data.ephemeral_history.length > 0) {
        console.log("Loading ephemeral chat history:", data.ephemeral_history.length, "messages");

        // Clear any existing intro message
        clearIntroMessage();

        // Render ephemeral chat history
        data.ephemeral_history.forEach((msg) => {
          appendMessage({
            sender: msg.role === "user" ? "user" : "bot",
            text: msg.text,
            emotions: null,
            timeStr: null, // No timestamps for ephemeral messages
          });
        });
      }
    } catch (err) {
      if (summaryEl) summaryEl.textContent = `Context error: ${err.message}`;
    }
  }

  async function sendMessage(text) {
    // Check if button is already disabled (cooldown active or processing)
    if (sendBtn.disabled && sendBtn.textContent.includes("Wait")) {
      return;
    }

    // Check rate limit (only if we have a previous message time)
    if (lastMessageTime > 0) {
      const now = Date.now();
      const timeSinceLastMessage = now - lastMessageTime;

      if (timeSinceLastMessage < RATE_LIMIT_MS) {
        const secondsLeft = Math.ceil((RATE_LIMIT_MS - timeSinceLastMessage) / 1000);
        appendMessage({
          sender: "bot",
          text: `⏱️ Please wait ${secondsLeft} more second${secondsLeft > 1 ? "s" : ""} before sending another message.`,
        });
        startCooldownTimer();
        return;
      }
    }

    // Check consent status before sending
    if (consentStatus === null) {
      showConsentModal();
      return;
    }

    if (!text || !text.trim()) {
      return;
    }

    const payload = {
      message: text.trim(),
      tone: toneSelect ? toneSelect.value : undefined,
      language: languageSelect ? languageSelect.value : undefined,
    };
    try {
      // Disable send button while processing (but don't start cooldown yet)
      sendBtn.disabled = true;
      sendBtn.textContent = "Sending...";

      // Add user message
      appendMessage({ sender: "user", text: payload.message, emotions: null });

      // Clear the input immediately
      messageInput.value = "";
      messageInput.style.height = "auto";

      // Show thinking indicator
      showThinkingIndicator();

      const res = await fetch("/api/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken() || document.querySelector("[name=csrfmiddlewaretoken]")?.value || "",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      // Handle rate limit from backend
      if (res.status === 429) {
        hideThinkingIndicator();
        appendMessage({
          sender: "bot",
          text: `⏱️ ${data.error || "Please wait before sending another message."}`,
        });
        // Update last message time to prevent bypass
        lastMessageTime = Date.now();
        if (data.retry_after) {
          startCooldownTimer();
        }
        return;
      }

      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);

      // Hide thinking indicator
      hideThinkingIndicator();

      appendMessage({ sender: "bot", text: data.reply });

      // Update last message time AFTER successful response
      lastMessageTime = Date.now();

      // Reload chat history to ensure updated conversation context
      loadChatHistory();

      // Update context panel
      if (summaryEl) summaryEl.textContent = data.summary || "";
      if (memoryEl) memoryEl.innerHTML = renderMemory(data.memory);
    } catch (err) {
      hideThinkingIndicator();
      appendMessage({ sender: "bot", text: `Sorry, I hit an error: ${err.message}` });
    } finally {
      // Start cooldown timer AFTER AI response (or error)
      startCooldownTimer();
      messageInput.focus();
    }
  }

  // Consent Management Functions
  async function checkConsentStatus() {
    try {
      const response = await fetch("/api/consent/status/", {
        method: "GET",
        headers: {
          "X-CSRFToken": getCSRFToken(),
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      consentStatus = data.consent_status;
      updateConsentUI();
      return consentStatus;
    } catch (error) {
      console.error("Error checking consent status:", error);
      // Set to null if there's an error, which will show "Set Privacy"
      consentStatus = null;
      updateConsentUI();
      return null;
    }
  }

  function updateConsentUI() {
    // Update desktop consent status button
    if (consentStatusElement) {
      if (consentStatus === true) {
        consentStatusElement.innerHTML = '<span class="consent-indicator secure">🛡️ Secure</span>';
        consentStatusElement.title = "Data stored securely with encryption";
      } else if (consentStatus === false) {
        consentStatusElement.innerHTML = '<span class="consent-indicator ephemeral">👤 Private</span>';
        consentStatusElement.title = "Ephemeral mode - no data stored";
      } else {
        consentStatusElement.innerHTML = '<span class="consent-indicator unknown">⚙️ Set Privacy</span>';
        consentStatusElement.title = "Click to set your privacy preference";
      }
    }

    // Update mobile menu consent text
    const mobileConsentText = document.getElementById("mobile-consent-text");
    if (mobileConsentText) {
      if (consentStatus === true) {
        mobileConsentText.textContent = "Storage: Secure";
      } else if (consentStatus === false) {
        mobileConsentText.textContent = "Storage: Private";
      } else {
        mobileConsentText.textContent = "Storage Settings";
      }
    }

    // Update ephemeral warning visibility
    if (ephemeralWarning) {
      ephemeralWarning.style.display = consentStatus === false ? "flex" : "none";
    }
  }

  function showConsentModal() {
    if (consentModal && consentOverlay) {
      // Reset selection
      selectedConsent = consentStatus;
      updateConsentSelection();

      consentModal.classList.add("show");
      consentOverlay.classList.add("active");
      document.body.style.overflow = "hidden";
    }
  }

  function hideConsentModal() {
    if (consentModal && consentOverlay) {
      consentModal.classList.remove("show");
      consentOverlay.classList.remove("active");
      document.body.style.overflow = "";
      selectedConsent = null;
    }
  }

  function updateConsentSelection() {
    consentOptions.forEach((option) => {
      const isSelected = option.dataset.consent === String(selectedConsent);
      option.classList.toggle("selected", isSelected);
    });
  }

  async function updateConsent(consent) {
    try {
      const response = await fetch("/api/consent/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        body: JSON.stringify({ consent }),
      });

      if (response.ok) {
        const data = await response.json();
        consentStatus = consent;
        updateConsentUI();
        hideConsentModal();

        // Show feedback message
        const feedback = consent ? "Privacy setting updated: Secure storage enabled" : "Privacy setting updated: Ephemeral mode enabled";
        appendMessage({ sender: "system", text: feedback });

        return true;
      } else {
        throw new Error("Failed to update consent");
      }
    } catch (error) {
      console.error("Error updating consent:", error);
      appendMessage({ sender: "system", text: "Error updating privacy setting. Please try again." });
      return false;
    }
  }

  function getCSRFToken() {
    const cookies = document.cookie.split(";");
    for (let cookie of cookies) {
      const [name, value] = cookie.trim().split("=");
      if (name === "csrftoken") {
        return value;
      }
    }
    return "";
  }

  // Send button click
  if (sendBtn) {
    sendBtn.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      const message = messageInput.value.trim();
      if (message && !sendBtn.disabled) {
        sendMessage(message);
      }
      return false;
    });
  }

  // Enter to send (Shift+Enter for new line)
  if (messageInput) {
    messageInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        const message = messageInput.value.trim();
        if (message && !sendBtn.disabled) {
          sendMessage(message);
        }
        return false;
      }
    });
  }

  // Clear intro message when user starts chatting
  function clearIntroMessage() {
    const introMessage = chatMessages.querySelector(".intro-message");
    if (introMessage) {
      introMessage.remove();
    }
  }

  // New chat functionality
  async function startNewChat() {
    try {
      const res = await fetch("/api/chat/new/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")?.value || "",
        },
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);

      // Clear current chat
      chatMessages.innerHTML = `
                <div class="intro-message">
                    <div class="intro-content">
                        <div class="intro-header">
                            <span class="intro-avatar">🍄</span>
                            <span class="intro-name">EnokiAI</span>
                        </div>
                        <div class="intro-text">
                            Hello! I'm EnokiAI, your mental health companion. I'm here to listen, support, and help you navigate your thoughts and feelings in a safe, non-judgmental space.
                        </div>
                        <div class="intro-features">
                            <h4>What I can help with:</h4>
                            <ul>
                                <li>Active listening and emotional support</li>
                                <li>Stress management techniques</li>
                                <li>Mindfulness and coping strategies</li>
                                <li>General mental wellness guidance</li>
                            </ul>
                        </div>
                        <div class="intro-text" style="margin-top: 1rem; font-style: italic; font-size: 0.9rem; color: #718096;">
                            Remember: I'm here to support you, but I'm not a replacement for professional mental health care. If you're experiencing a crisis, please reach out to a mental health professional or crisis helpline.
                        </div>
                    </div>
                </div>
            `;

      // Update context
      if (summaryEl) summaryEl.textContent = "";
      if (memoryEl) memoryEl.innerHTML = "<em>No memory yet.</em>";

      // Refresh chat history to show the new chat
      loadChatHistory();

      console.log("New chat started:", data.session_id);
    } catch (err) {
      console.error("Error starting new chat:", err);
      alert("Failed to start new chat. Please try again.");
    }
  }

  // Load chat history
  async function loadChatHistory() {
    try {
      const res = await fetch("/api/chat/history/", {
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);

      renderChatHistory(data.sessions);
    } catch (err) {
      console.error("Error loading chat history:", err);
      chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">Failed to load chat history</p>';
    }
  }

  // Render chat history
  function renderChatHistory(sessions) {
    if (!sessions || sessions.length === 0) {
      chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">No chat history yet</p>';
      return;
    }

    // Filter out sessions with invalid dates
    const validSessions = sessions.filter(session => session.updated_at);
    
    if (validSessions.length === 0) {
      chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">No chat history yet</p>';
      return;
    }

    chatSessionsList.innerHTML = validSessions
      .map(
        (session) => `
            <div class="chat-session ${session.is_current ? "active" : ""}" data-session-id="${session.id}">
                <div class="session-header">
                    <div class="session-title">${session.title || "Chat Session"}</div>
                    <button class="session-delete-btn" data-session-id="${session.id}" title="Delete chat">
                        🗑️
                    </button>
                </div>
                <div class="session-preview">${session.preview || "No messages yet"}</div>
                <div class="session-meta">
                    <span>${session.message_count} messages</span>
                    <span>${formatDate(session.updated_at)}</span>
                </div>
            </div>
        `
      )
      .join("");

    // Add click handlers for session selection
    document.querySelectorAll(".chat-session").forEach((sessionEl) => {
      sessionEl.addEventListener("click", function (e) {
        // Don't load session if clicking delete button
        if (e.target.classList.contains("session-delete-btn")) {
          return;
        }
        const sessionId = this.dataset.sessionId;
        loadChatSession(sessionId);
      });
    });

    // Add click handlers for delete buttons
    document.querySelectorAll(".session-delete-btn").forEach((deleteBtn) => {
      deleteBtn.addEventListener("click", function (e) {
        e.stopPropagation(); // Prevent session loading
        const sessionId = this.dataset.sessionId;
        deleteChatSession(sessionId);
      });
    });
  }

  // Delete chat session
  async function deleteChatSession(sessionId) {
    if (!confirm("Are you sure you want to delete this chat? This action cannot be undone.")) {
      return;
    }

    try {
      const response = await fetch(`/api/chat/delete/${sessionId}/`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error("Failed to delete chat session");
      }

      const data = await response.json();

      // If the deleted session was the current one, reload the page to start a new session
      if (data.was_current_session) {
        window.location.reload();
      } else {
        // Otherwise, just refresh the history list
        loadChatHistory();
      }
    } catch (error) {
      console.error("Error deleting chat session:", error);
      alert("Failed to delete chat session. Please try again.");
    }
  }

  // Load specific chat session
  async function loadChatSession(sessionId) {
    try {
      // First, switch to this session on the backend
      const switchRes = await fetch(`/api/chat/switch/${sessionId}/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")?.value || "",
        },
        credentials: "same-origin",
      });
      const switchData = await switchRes.json();
      if (!switchRes.ok || switchData.error) throw new Error(switchData.error || `HTTP ${switchRes.status}`);

      // Now get the session details
      const res = await fetch(`/api/chat/session/${sessionId}/`, {
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);

      // Clear current chat and load session messages
      chatMessages.innerHTML = "";
      data.messages.forEach((message) => {
        appendMessage({
          sender: message.sender,
          text: message.text,
          emotions: message.emotions,
          timeStr: formatTime(message.created_at),
        });
      });

      // Update context
      if (summaryEl) summaryEl.textContent = data.summary || "";
      if (memoryEl) memoryEl.innerHTML = renderMemory(data.memory);

      // Update history highlighting - remove active class from all, add to current
      document.querySelectorAll(".chat-session").forEach((session) => {
        session.classList.remove("active");
        if (session.dataset.sessionId === String(sessionId)) {
          session.classList.add("active");
        }
      });

      // Close history panel
      closeHistoryPanel();

      console.log("Loaded chat session:", sessionId);
    } catch (err) {
      console.error("Error loading chat session:", err);
      alert("Failed to load chat session. Please try again.");
    }
  }

  // Format date for display
  function formatDate(dateStr) {
    // Handle null, undefined, or empty date strings
    if (!dateStr) return "";
    
    const date = new Date(dateStr);
    
    // Handle invalid dates
    if (isNaN(date.getTime())) return "";
    
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    // Handle negative differences (future dates or timezone mismatches)
    if (diffDays < 0) return "Today";
    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString();
  }

  // Format time for message display
  function formatTime(dateStr) {
    return new Date(dateStr).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // Refresh context button
  if (refreshBtn)
    refreshBtn.addEventListener("click", function () {
      fetchContext();
    });

  // Helper function to check if current chat has any messages
  function hasMessages() {
    const messages = chatMessages.querySelectorAll(".chat-message, .thinking-indicator");
    return messages.length > 0;
  }

  // New chat button
  if (newChatBtn)
    newChatBtn.addEventListener("click", function () {
      if (!hasMessages()) {
        alert("Start a conversation first before creating a new chat.");
        return;
      }
      if (confirm("Start a new chat? Your current conversation will be saved to history.")) {
        startNewChat();
      }
    });

  // New chat button in history panel (large screens)
  const newChatBtnHistory = document.getElementById("new-chat-btn-history");
  if (newChatBtnHistory)
    newChatBtnHistory.addEventListener("click", function () {
      if (!hasMessages()) {
        alert("Start a conversation first before creating a new chat.");
        return;
      }
      if (confirm("Start a new chat? Your current conversation will be saved to history.")) {
        startNewChat();
      }
    });

  // Initial behaviors
  scrollToBottom();
  fetchContext();
  checkConsentStatus();
  loadChatHistory();
});
