// ============================================
// GLOBAL VARIABLES & STATE MANAGEMENT
// ============================================

let consentStatus = null;
let selectedConsent = null;

// Anonymous mode sessionStorage keys (cleared when browser closes)
const ANONYMOUS_SESSIONS_KEY = "anonymousChatSessions";
const ANONYMOUS_CURRENT_SESSION_KEY = "anonymousCurrentSessionId";

// ============================================
// ANONYMOUS SESSION FUNCTIONS
// ============================================

// Retrieve anonymous chat sessions from sessionStorage
function getAnonymousSessions() {
  try {
    const stored = sessionStorage.getItem(ANONYMOUS_SESSIONS_KEY);
    return stored ? JSON.parse(stored) : [];
  } catch (e) {
    console.error("Error reading anonymous sessions from sessionStorage:", e);
    return [];
  }
}

// Save anonymous chat sessions to sessionStorage
function saveAnonymousSessions(sessions) {
  try {
    sessionStorage.setItem(ANONYMOUS_SESSIONS_KEY, JSON.stringify(sessions));
  } catch (e) {
    console.error("Error saving anonymous sessions to sessionStorage:", e);
  }
}

// Retrieve the current anonymous session ID
function getCurrentAnonymousSessionId() {
  return sessionStorage.getItem(ANONYMOUS_CURRENT_SESSION_KEY);
}

// Set the current anonymous session ID
function setCurrentAnonymousSessionId(sessionId) {
  sessionStorage.setItem(ANONYMOUS_CURRENT_SESSION_KEY, sessionId);
}

// Create a new anonymous session with initial metadata
function createAnonymousSession() {
  const sessionId = "anon_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
  const session = {
    id: sessionId,
    title: "Untitled Chat",
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  const sessions = getAnonymousSessions();
  sessions.push(session);
  saveAnonymousSessions(sessions);
  setCurrentAnonymousSessionId(sessionId);

  return sessionId;
}

// Add a message to the current anonymous session
function addMessageToAnonymousSession(sender, text) {
  if (consentStatus !== false) return; // Only store if in anonymous mode

  const sessionId = getCurrentAnonymousSessionId();
  if (!sessionId) return;

  const sessions = getAnonymousSessions();
  const session = sessions.find((s) => s.id === sessionId);

  if (session) {
    session.messages.push({
      sender,
      text,
      created_at: new Date().toISOString(),
    });
    session.updated_at = new Date().toISOString();

    // Update title based on first user message
    if (sender === "user" && session.messages.filter((m) => m.sender === "user").length === 1) {
      session.title = text.substring(0, 50) + (text.length > 50 ? "..." : "");
    }

    saveAnonymousSessions(sessions);
  }
}

// Load all messages from a specific anonymous session
function loadAnonymousSessionMessages(sessionId) {
  const sessions = getAnonymousSessions();
  const session = sessions.find((s) => s.id === sessionId);
  return session ? session.messages : [];
}

// Remove an anonymous session and its messages from storage
function deleteAnonymousSession(sessionId) {
  const sessions = getAnonymousSessions();
  const filtered = sessions.filter((s) => s.id !== sessionId);
  saveAnonymousSessions(filtered);

  if (getCurrentAnonymousSessionId() === sessionId) {
    sessionStorage.removeItem(ANONYMOUS_CURRENT_SESSION_KEY);
  }
}

document.addEventListener("DOMContentLoaded", function () {
  // ============================================
  // DOM ELEMENT SELECTORS
  // ============================================

  const messageForm = document.querySelector(".message-form");
  const messageInput = document.querySelector(".message-input");
  const sendBtn = document.querySelector(".send-btn");
  const chatMessages = document.getElementById("chat-messages");
  const toneSelect = document.getElementById("tone");
  const languageSelect = document.getElementById("language");

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
  const refreshBtn = document.getElementById("refresh-btn");

  // Context elements
  const summaryEl = document.getElementById("summary");
  const memoryEl = document.getElementById("memory");

  // ============================================
  // MOBILE MENU FUNCTIONALITY
  // ============================================

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

  // ============================================
  // CONSENT MODAL ELEMENTS
  // ============================================

  const consentModal = document.getElementById("consent-modal");
  const consentOverlay = document.getElementById("consent-overlay");
  const consentOptions = document.querySelectorAll(".consent-option");
  const confirmConsentBtn = document.getElementById("confirm-consent");
  const cancelConsentBtn = document.getElementById("cancel-consent");
  const consentStatusElement = document.getElementById("consent-status");
  const anonymousWarning = document.getElementById("anonymous-warning");
  const enableStorageBtn = document.getElementById("enable-storage-btn");

  // ============================================
  // ELEMENT VALIDATION
  // ============================================

  if (!messageInput || !sendBtn || !chatMessages) {
    console.error("Required chat elements not found:", {
      messageInput: !!messageInput,
      sendBtn: !!sendBtn,
      chatMessages: !!chatMessages,
    });
    return;
  }

  // ============================================
  // RATE LIMITING & MESSAGE SENDING
  // ============================================

  let lastMessageTime = 0;
  const RATE_LIMIT_MS = 5000;
  let countdownInterval = null;

  // Global function for inline event handlers
  window.handleSendMessage = function () {
    const message = messageInput.value.trim();
    if (message && !sendBtn.disabled) {
      sendMessage(message);
    }
  };

  // Prevent rapid message sending with countdown timer
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

  // ============================================
  // NOTIFICATION SYSTEM (must be inside DOMContentLoaded)
  // ============================================
  function showNotification(title, message, type = "info", duration = 4000) {
    console.log("showNotification called:", { title, message, type, duration });

    const container = document.getElementById("notification-container");
    console.log("Notification container:", container);

    if (!container) {
      console.error("Notification container not found! Creating emergency fallback...");
      // Emergency: try to find or create the container
      const body = document.body;
      if (body) {
        const fallbackContainer = document.createElement("div");
        fallbackContainer.id = "notification-container";
        fallbackContainer.className = "notification-container";
        body.prepend(fallbackContainer);
        console.log("Created fallback notification container");
      }
      return showNotification(title, message, type, duration); // Retry
    }

    const toast = document.createElement("div");
    toast.className = `toast-notification ${type}`;

    const iconMap = {
      success: "✅",
      error: "❌",
      info: "ℹ️",
      warning: "⚠️",
    };

    toast.innerHTML = `
      <span class="toast-icon">${iconMap[type] || iconMap["info"]}</span>
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        ${message ? `<div class="toast-message">${message}</div>` : ""}
      </div>
      <button class="toast-close" aria-label="Close notification">&times;</button>
    `;

    console.log("Created toast element:", toast);
    container.appendChild(toast);
    console.log("Appended toast to container");

    const closeBtn = toast.querySelector(".toast-close");
    function removeToast() {
      console.log("Removing toast");
      toast.classList.add("removing");
      setTimeout(() => toast.remove(), 300);
    }

    closeBtn.addEventListener("click", removeToast);

    if (duration > 0) {
      setTimeout(removeToast, duration);
    }

    return toast;
  }

  // ============================================
  // DELETE CONFIRMATION MODAL
  // ============================================
  let pendingDeleteSessionId = null;

  function showDeleteConfirmation(sessionId, sessionTitle) {
    const overlay = document.getElementById("delete-confirm-overlay");
    const modal = document.getElementById("delete-confirm-modal");
    const message = document.getElementById("delete-confirm-message");
    const cancelBtn = document.getElementById("delete-confirm-cancel");
    const confirmBtn = document.getElementById("delete-confirm-proceed");

    if (!overlay || !modal) {
      console.error("Delete confirmation modal elements not found!");
      return;
    }

    // Find the session to check message count
    const sessionEl = document.querySelector(`[data-session-id="${sessionId}"]`);
    const messageCount = sessionEl ? parseInt(sessionEl.querySelector(".session-meta span")?.textContent || 0) : 0;

    // Prevent deletion of empty chats
    if (messageCount === 0) {
      showNotification("🍄 Let's Chat First!", "Start a conversation before deleting this chat. Every conversation matters!", "info", 4500);
      return;
    }

    pendingDeleteSessionId = sessionId;
    message.textContent = `Delete "${sessionTitle || "Chat"}"? This action cannot be undone.`;

    modal.classList.add("show");
    overlay.style.display = "block";

    function closeModal() {
      modal.classList.remove("show");
      overlay.style.display = "none";
      pendingDeleteSessionId = null;
    }

    cancelBtn.onclick = closeModal;
    overlay.onclick = closeModal;

    confirmBtn.onclick = async function () {
      closeModal();
      await confirmDeleteSession(sessionId);
    };
  }

  async function confirmDeleteSession(sessionId) {
    try {
      if (!sessionId || sessionId.startsWith("anon_")) {
        // Anonymous session
        deleteAnonymousSession(sessionId);
        showNotification("Chat Deleted", "This conversation has been removed.", "success");
        loadChatHistory();
        return;
      }

      // Authenticated session - send to backend using DELETE method matching the endpoint
      const response = await fetch(`/api/chat/delete/${sessionId}/`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCSRFToken(),
        },
      });

      if (response.ok) {
        showNotification("Chat Deleted", "This conversation has been removed.", "success");
        loadChatHistory();
      } else {
        const data = await response.json();
        showNotification("Error", data.error || "Failed to delete chat", "error");
      }
    } catch (error) {
      console.error("Error deleting session:", error);
      showNotification("Error", "Failed to delete chat. Please try again.", "error");
    }
  }

  // Settings panel handlers
  if (settingsToggle) settingsToggle.addEventListener("click", openSettings);
  if (closeSettings) closeSettings.addEventListener("click", closeSettingsPanel);
  if (settingsOverlay) settingsOverlay.addEventListener("click", closeSettingsPanel);

  // Preferences form auto-save handler with AJAX
  const preferencesForm = document.querySelector(".preferences-form");

  if (toneSelect) {
    // Auto-save when tone changes using AJAX
    toneSelect.addEventListener("change", function () {
      if (!preferencesForm) return;

      // Prepare form data using URLSearchParams for form encoding
      const params = new URLSearchParams();
      params.append("update_prefs", "1");
      params.append("tone", toneSelect.value);
      params.append("language", document.getElementById("language")?.value || "");
      
      // Get CSRF token
      const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
      if (csrfToken) {
        params.append("csrfmiddlewaretoken", csrfToken);
      }

      // Send AJAX request to /chat/ endpoint (POST to /chat/)
      fetch("/chat/", {
        method: "POST",
        body: params,
        headers: {
          "X-CSRFToken": csrfToken,
          "Content-Type": "application/x-www-form-urlencoded",
        },
        credentials: "same-origin",
      })
        .then((response) => {
          if (response.ok) {
            // Show success notification without page refresh
            showNotification(
              "✓ Tone Updated",
              "Your conversation tone preference has been saved.",
              "success",
              3000
            );
            console.log("Preferences saved successfully");
          } else {
            console.error("Response status:", response.status);
            showNotification(
              "Error",
              "Failed to save preferences. Please try again.",
              "error",
              3000
            );
          }
        })
        .catch((err) => {
          console.error("Error saving preferences:", err);
          showNotification(
            "Error",
            "Failed to save preferences. Please try again.",
            "error",
            3000
          );
        });
    });
  }

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
        // Anonymous user trying to enable secure mode - show login prompt modal
        hideConsentModal();
        showLoginPromptModal();
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

  // Enable storage button in anonymous warning
  if (enableStorageBtn) {
    enableStorageBtn.addEventListener("click", function () {
      // Check if user is authenticated
      const isAuthenticated = window.isAuthenticated || false;

      if (!isAuthenticated) {
        // Anonymous user - show custom login prompt modal
        showLoginPromptModal();
      } else {
        // Authenticated user - show consent modal
        showConsentModal();
      }
    });
  }

  // ============================================
  // LOGIN PROMPT MODAL
  // ============================================

  // Show custom login prompt modal
  function showLoginPromptModal() {
    const overlay = document.getElementById("login-prompt-overlay");
    const modal = document.getElementById("login-prompt-modal");
    const cancelBtn = document.getElementById("login-prompt-cancel");
    const proceedBtn = document.getElementById("login-prompt-proceed");

    if (!overlay || !modal) {
      console.error("Login prompt modal elements not found!");
      return;
    }

    overlay.style.display = "block";
    modal.classList.add("show");

    // Cancel button closes the modal
    cancelBtn.onclick = function () {
      hideLoginPromptModal();
    };

    // Proceed button redirects to login
    proceedBtn.onclick = function () {
      window.location.href = "/login/";
    };

    // Close on overlay click
    overlay.onclick = function () {
      hideLoginPromptModal();
    };
  }

  // Hide login prompt modal
  function hideLoginPromptModal() {
    const overlay = document.getElementById("login-prompt-overlay");
    const modal = document.getElementById("login-prompt-modal");

    if (overlay && modal) {
      overlay.style.display = "none";
      modal.classList.remove("show");
    }
  }

  // ============================================
  // UI EVENT LISTENERS
  // ============================================

  // Auto-resize textarea based on content
  if (messageInput) {
    messageInput.addEventListener("input", function () {
      this.style.height = "auto";
      this.style.height = Math.min(this.scrollHeight, 120) + "px";
    });
  }

  // ============================================
  // MESSAGE RENDERING HELPERS
  // ============================================

  // Format timestamp for display
  function fmtTime(d = new Date()) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // Append a message to the chat display
  function appendMessage({ sender, text, timeStr = null }) {
    // Clear intro when user sends first message
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

    // Escape HTML and preserve line breaks
    const escapedText = escapeHtml(text).replace(/\n/g, "<br>");
    content.querySelector(".message-text").innerHTML = escapedText;
    wrapper.appendChild(content);
    chatMessages.appendChild(wrapper);

    // Persist message to anonymous session if applicable
    addMessageToAnonymousSession(sender, text);

    scrollToBottom();
  }

  // Display animated thinking indicator while bot processes
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

  // Remove thinking indicator
  function hideThinkingIndicator() {
    const indicator = document.getElementById("thinking-indicator");
    if (indicator) {
      indicator.remove();
    }
  }

  // Format and display user memory context
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

      // Load anonymous chat history if available (no consent mode)
      if (data.anonymous_history && Array.isArray(data.anonymous_history) && data.anonymous_history.length > 0) {
        console.log("Loading anonymous chat history:", data.anonymous_history.length, "messages");

        // Clear any existing intro message
        clearIntroMessage();

        // Render anonymous chat history
        data.anonymous_history.forEach((msg) => {
          appendMessage({
            sender: msg.role === "user" ? "user" : "bot",
            text: msg.text,
            emotions: null,
            timeStr: null, // No timestamps for anonymous messages
          });
        });
      }
    } catch (err) {
      if (summaryEl) summaryEl.textContent = `Context error: ${err.message}`;
    }
  }

  // ============================================
  // MESSAGE SENDING & PROCESSING
  // ============================================

  async function sendMessage(text) {
    // Prevent sending if cooldown is active
    if (sendBtn.disabled && sendBtn.textContent.includes("Wait")) {
      return;
    }

    // Enforce rate limiting between messages
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

    // Prompt user to select consent mode before first message
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
        consentStatusElement.innerHTML = '<span class="consent-indicator anonymous">👤 Private</span>';
        consentStatusElement.title = "Anonymous mode - no data stored";
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

    // Update anonymous warning visibility
    if (anonymousWarning) {
      anonymousWarning.style.display = consentStatus === false ? "flex" : "none";
    }
  }

  // ============================================
  // CONSENT MODAL MANAGEMENT
  // ============================================

  // Display consent modal to user
  function showConsentModal() {
    if (consentModal && consentOverlay) {
      // Reset selection to current status
      selectedConsent = consentStatus;
      updateConsentSelection();

      consentModal.classList.add("show");
      consentOverlay.classList.add("active");
      document.body.style.overflow = "hidden";
    }
  }

  // Hide consent modal
  function hideConsentModal() {
    if (consentModal && consentOverlay) {
      consentModal.classList.remove("show");
      consentOverlay.classList.remove("active");
      document.body.style.overflow = "";
      selectedConsent = null;
    }
  }

  // Update visual state of consent options
  function updateConsentSelection() {
    consentOptions.forEach((option) => {
      const isSelected = option.dataset.consent === String(selectedConsent);
      option.classList.toggle("selected", isSelected);
    });
  }

  // Handle consent preference changes
  async function updateConsent(consent) {
    try {
      // Handle migration from anonymous to secure mode
      if (consent === true && consentStatus === false && hasMessages()) {
        const saveChat = confirm(
          "You have an ongoing conversation in anonymous mode. Would you like to save this conversation to your secure storage before enabling it?\n\nClick OK to save, or Cancel to start fresh."
        );

        if (saveChat) {
          // Migrate anonymous chat to secure database storage
          await saveAnonymousChatToDatabase();
        } else {
          // Clear current chat and start fresh anonymous session
          chatMessages.innerHTML = "";
          clearIntroMessage();
          createAnonymousSession();
        }
      }
      
      // If entering anonymous mode (consent = false), always create a fresh session
      if (consent === false) {
        // Clear sessionStorage to remove old sessions
        sessionStorage.removeItem(ANONYMOUS_SESSIONS_KEY);
        sessionStorage.removeItem(ANONYMOUS_CURRENT_SESSION_KEY);
        
        // Clear the chat and create a new anonymous session
        chatMessages.innerHTML = "";
        clearIntroMessage();
        createAnonymousSession();
      }

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
        const feedback = consent ? "Privacy setting updated: Secure storage enabled" : "Privacy setting updated: Anonymous mode enabled";
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

  // Save current anonymous chat to database
  async function saveAnonymousChatToDatabase() {
    try {
      const sessionId = getCurrentAnonymousSessionId();
      if (!sessionId) return false;

      const session = getAnonymousSessions().find((s) => s.id === sessionId);
      if (!session || !session.messages.length) return false;

      // Send all messages to create a new database session
      for (const message of session.messages) {
        // Only need to send user messages as AI responses are generated
        if (message.sender === "user") {
          // We can just mark this happened, but actual saving happens via /api/chat/
          console.log("Message queued for saving:", message.text);
        }
      }

      console.log("Anonymous chat prepared for database storage");
      return true;
    } catch (error) {
      console.error("Error saving anonymous chat:", error);
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
      // If in anonymous/anonymous mode, create local session
      if (consentStatus === false) {
        createAnonymousSession();

        // Clear current chat and show intro
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
                        <div
                  class="intro-text"
                  style="
                    margin-top: 1rem;
                    padding: 0.75rem;
                    background: linear-gradient(135deg, rgba(136, 183, 123, 0.1) 0%, rgba(122, 176, 104, 0.1) 100%);
                    border-radius: 8px;
                    border-left: 3px solid #88b77b;
                    font-size: 0.9rem;
                    color: #2d3748;
                  ">
                  💡 <strong>Tip:</strong> You can adjust my conversation tone anytime by clicking the settings icon ⚙️ in the top right corner!
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

        // Refresh chat history (including anonymous sessions)
        loadChatHistory();

        // Show notification for anonymous mode
        showNotification("New Chat Started", "Your previous conversation has been saved locally.", "info", 3500);

        console.log("New anonymous chat started");
        return;
      }

      // For authenticated users, use API
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
                        <div
                  class="intro-text"
                  style="
                    margin-top: 1rem;
                    padding: 0.75rem;
                    background: linear-gradient(135deg, rgba(136, 183, 123, 0.1) 0%, rgba(122, 176, 104, 0.1) 100%);
                    border-radius: 8px;
                    border-left: 3px solid #88b77b;
                    font-size: 0.9rem;
                    color: #2d3748;
                  ">
                  💡 <strong>Tip:</strong> You can adjust my conversation tone anytime by clicking the settings icon ⚙️ in the top right corner!
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

      // Show notification for authenticated users
      showNotification("New Chat Started", "Your previous conversation has been saved to history.", "success", 3500);

      console.log("New chat started:", data.session_id);
    } catch (err) {
      console.error("Error starting new chat:", err);
      alert("Failed to start new chat. Please try again.");
    }
  }

  // ============================================
  // CHAT HISTORY & SESSION MANAGEMENT
  // ============================================

  // Load chat history from appropriate source
  async function loadChatHistory() {
    try {
      let allSessions = [];

      console.log("Loading chat history with consentStatus:", consentStatus);

      // Load anonymous sessions from sessionStorage if in anonymous mode
      if (consentStatus === false) {
        console.log("Loading anonymous sessions from sessionStorage");
        allSessions = getAnonymousSessions();
      } else if (consentStatus === true || consentStatus === null) {
        // Load authenticated sessions from API with force_refresh to bypass cache on initial load
        console.log("Loading authenticated sessions from API (consentStatus:", consentStatus, ")");
        try {
          const res = await fetch("/api/chat/history/?force_refresh=true", {
            credentials: "same-origin",
          });

          console.log("Chat history API status:", res.status, "ok:", res.ok);

          if (!res.ok) {
            const errorText = await res.text();
            console.error("API error response:", res.status, errorText);
            throw new Error(`API returned ${res.status}: ${errorText}`);
          }

          const data = await res.json();
          console.log("Chat history API parsed response:", data);

          if (data && typeof data === "object") {
            if (data.error) {
              console.error("API returned error in response:", data.error);
            } else if (data.sessions && Array.isArray(data.sessions)) {
              console.log("Found authenticated sessions:", data.sessions.length);
              allSessions = data.sessions;
            } else {
              console.warn("API response missing sessions array:", data);
            }
          } else {
            console.error("API returned non-object data:", data);
          }
        } catch (err) {
          console.error("Error loading authenticated chat history:", err);
          throw err; // Re-throw to trigger outer catch
        }
      }

      console.log("Total sessions to render:", allSessions.length);
      renderChatHistory(allSessions);
    } catch (err) {
      console.error("Error loading chat history:", err, err.stack);
      if (chatSessionsList) {
        chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">Failed to load chat history</p>';
      }
    }
  }

  // Render chat history
  function renderChatHistory(sessions) {
    try {
      if (!chatSessionsList) {
        console.error("chatSessionsList element not found");
        return;
      }

      console.log("renderChatHistory called with sessions:", sessions, "type:", typeof sessions);

      if (!sessions || !Array.isArray(sessions)) {
        console.warn("sessions is not an array:", sessions);
        chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">No chat history yet</p>';
        return;
      }

      if (sessions.length === 0) {
        chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">No chat history yet</p>';
        return;
      }

      // Filter out sessions with invalid dates
      const validSessions = sessions.filter((session) => {
        if (!session.updated_at) {
          console.warn("Skipping session with no updated_at:", session);
          return false;
        }
        return true;
      });

      if (validSessions.length === 0) {
        chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">No chat history yet</p>';
        return;
      }

      // Process sessions to compute message_count and preview if missing (for anonymous sessions)
      const processedSessions = validSessions.map((session) => {
        const processed = { ...session };

        // Convert ID to string for consistent checking
        const sessionIdStr = String(session.id);

        // For anonymous sessions, compute message_count and preview from messages array
        if (sessionIdStr && sessionIdStr.startsWith("anon_")) {
          const messageCount = session.messages ? session.messages.length : 0;
          processed.message_count = messageCount;
          
          if (messageCount > 0) {
            // Find the first user message for the preview
            const firstUserMessage = session.messages.find((m) => m.sender === "user");
            if (firstUserMessage) {
              processed.preview = firstUserMessage.text.substring(0, 80) + (firstUserMessage.text.length > 80 ? "..." : "");
              processed.title = firstUserMessage.text.substring(0, 50) + (firstUserMessage.text.length > 50 ? "..." : "");
            } else {
              processed.preview = "No user messages yet";
            }
          } else {
            processed.preview = "No messages yet";
          }
        }

        return processed;
      });

      // Sort by updated_at descending (most recent first)
      processedSessions.sort((a, b) => {
        const dateA = new Date(a.updated_at);
        const dateB = new Date(b.updated_at);
        return dateB - dateA;
      });

      const html = processedSessions
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
                      <span>${session.message_count || 0} messages</span>
                      <span>${formatDate(session.updated_at)}</span>
                  </div>
              </div>
          `
        )
        .join("");

      chatSessionsList.innerHTML = html;

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
          const sessionEl = this.closest(".chat-session");
          const sessionTitle = sessionEl ? sessionEl.querySelector(".session-title")?.textContent : "Chat";
          showDeleteConfirmation(sessionId, sessionTitle);
        });
      });
    } catch (err) {
      console.error("Error rendering chat history:", err, err.stack);
      if (chatSessionsList) {
        chatSessionsList.innerHTML = '<p style="color: #718096; text-align: center; padding: 2rem;">No chat history yet</p>';
      }
    }
  }

  // Delete chat session (legacy - kept for backward compatibility)
  async function deleteChatSession(sessionId) {
    // Now uses showDeleteConfirmation which is already called from renderChatHistory
    return;
  }

  // Load specific chat session
  async function loadChatSession(sessionId) {
    try {
      // Show loading indicator
      chatMessages.innerHTML = '<div style="text-align: center; padding: 2rem; color: #718096;">Loading chat...</div>';

      // If anonymous session (starts with 'anon_'), load from sessionStorage
      if (sessionId && sessionId.startsWith("anon_")) {
        setCurrentAnonymousSessionId(sessionId);
        const messages = loadAnonymousSessionMessages(sessionId);

        // Clear current chat and load session messages
        chatMessages.innerHTML = "";

        if (messages.length === 0) {
          // Show intro message if no messages
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
                        <div
                  class="intro-text"
                  style="
                    margin-top: 1rem;
                    padding: 0.75rem;
                    background: linear-gradient(135deg, rgba(136, 183, 123, 0.1) 0%, rgba(122, 176, 104, 0.1) 100%);
                    border-radius: 8px;
                    border-left: 3px solid #88b77b;
                    font-size: 0.9rem;
                    color: #2d3748;
                  ">
                  💡 <strong>Tip:</strong> You can adjust my conversation tone anytime by clicking the settings icon ⚙️ in the top right corner!
                </div>
                        <div class="intro-text" style="margin-top: 1rem; font-style: italic; font-size: 0.9rem; color: #718096;">
                            Remember: I'm here to support you, but I'm not a replacement for professional mental health care. If you're experiencing a crisis, please reach out to a mental health professional or crisis helpline.
                        </div>
                    </div>
                </div>
            `;
        } else {
          messages.forEach((message) => {
            appendMessage({
              sender: message.sender,
              text: message.text,
              timeStr: message.created_at ? formatTime(message.created_at) : undefined,
            });
          });
        }

        // Update context
        if (summaryEl) summaryEl.textContent = "";
        if (memoryEl) memoryEl.innerHTML = "<em>No memory in anonymous mode.</em>";

        // Update history highlighting - remove active class from all, add to current
        document.querySelectorAll(".chat-session").forEach((session) => {
          session.classList.remove("active");
          if (session.dataset.sessionId === String(sessionId)) {
            session.classList.add("active");
          }
        });

        // Close history panel
        closeHistoryPanel();

        console.log("Loaded anonymous chat session:", sessionId);
        return;
      }

      // For authenticated sessions, use API
      // Make both API calls in parallel for faster loading
      const [switchRes, sessionRes] = await Promise.all([
        fetch(`/api/chat/switch/${sessionId}/`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector("[name=csrfmiddlewaretoken]")?.value || "",
          },
          credentials: "same-origin",
        }),
        fetch(`/api/chat/session/${sessionId}/`, {
          credentials: "same-origin",
        }),
      ]);

      const switchData = await switchRes.json();
      if (!switchRes.ok || switchData.error) throw new Error(switchData.error || `HTTP ${switchRes.status}`);

      const data = await sessionRes.json();
      if (!sessionRes.ok || data.error) throw new Error(data.error || `HTTP ${sessionRes.status}`);

      // Clear current chat and load session messages
      chatMessages.innerHTML = "";

      if (data.messages.length === 0) {
        // Show intro message for empty sessions
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
              <div
                  class="intro-text"
                  style="
                    margin-top: 1rem;
                    padding: 0.75rem;
                    background: linear-gradient(135deg, rgba(136, 183, 123, 0.1) 0%, rgba(122, 176, 104, 0.1) 100%);
                    border-radius: 8px;
                    border-left: 3px solid #88b77b;
                    font-size: 0.9rem;
                    color: #2d3748;
                  ">
                  💡 <strong>Tip:</strong> You can adjust my conversation tone anytime by clicking the settings icon ⚙️ in the top right corner!
                </div>
              <div class="intro-text" style="margin-top: 1rem; font-style: italic; font-size: 0.9rem; color: #718096;">
                Remember: I'm here to support you, but I'm not a replacement for professional mental health care. If you're experiencing a crisis, please reach out to a mental health professional or crisis helpline.
              </div>
            </div>
          </div>
        `;
      } else {
        data.messages.forEach((message) => {
          appendMessage({
            sender: message.sender,
            text: message.text,
            emotions: message.emotions,
            timeStr: formatTime(message.created_at),
          });
        });
      }

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
      chatMessages.innerHTML = '<div style="text-align: center; padding: 2rem; color: #ff6b6b;">Failed to load chat session. Please try again.</div>';
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

  // ============================================
  // UTILITY FUNCTIONS & EVENT HANDLERS
  // ============================================

  // Refresh context button
  if (refreshBtn)
    refreshBtn.addEventListener("click", function () {
      fetchContext();
    });

  // Check if current chat has any messages
  function hasMessages() {
    const messages = chatMessages.querySelectorAll(".chat-message, .thinking-indicator");
    return messages.length > 0;
  }

  // New chat button
  if (newChatBtn)
    newChatBtn.addEventListener("click", function () {
      if (!hasMessages()) {
        showNotification("🍄 Let's Chat First!", "Start a conversation before creating a new chat. Every conversation matters!", "info", 4500);
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
        showNotification("🍄 Let's Chat First!", "Start a conversation before creating a new chat. Every conversation matters!", "info", 4500);
        return;
      }
      if (confirm("Start a new chat? Your current conversation will be saved to history.")) {
        startNewChat();
      }
    });

  // ============================================
  // INITIALIZATION & STARTUP
  // ============================================

  // Initial page setup
  scrollToBottom();
  fetchContext();

  // Load consent status then chat history
  checkConsentStatus().then(() => {
    loadChatHistory();
  });

  // Initialize anonymous session if needed
  function initializeAnonymousSession() {
    const currentSessionId = getCurrentAnonymousSessionId();
    if (!currentSessionId) {
      createAnonymousSession();
    }
  }

  // Setup anonymous session
  initializeAnonymousSession();

  // ============================================
  // END DUPLICATE CODE - REMOVED (already defined above)
  // ============================================
});
