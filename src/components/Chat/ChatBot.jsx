import './Chat.css'; // Should point to src/components/Chat/Chat.css
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaMoon, FaQuestionCircle, FaSignOutAlt, FaSun, FaUserCircle } from 'react-icons/fa';
import { FaCog } from 'react-icons/fa';

import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { useLocation } from '../../context/LocationContext';

import ChatHistory from './ChatHistory';
import MessageInput from './MessageInput';
import MessageList from './MessageList';
import QuickActions from './QuickActions';
import WeatherWidget from './WeatherWidget';
import SettingsModal from './SettingsModal';

import { storage } from '../../utils/storage';
import { queryAgent, saveChat } from '../../utils/agentApi';

const ChatBot = () => {
  const [messages, setMessages] = useState([]);
  const [history, setHistory] = useState([]);
  const [activeHistoryId, setActiveHistoryId] = useState(null);
  const [restoring, setRestoring] = useState(true);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [showHelp, setShowHelp] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { location } = useLocation();

  const navigate = useNavigate();
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const hasMessages = messages.length > 0;

  /* ---------- STORAGE HELPERS ---------- */
  const getChatMessagesKey = (chatId) => `chatMessages_${chatId}`;

  const getChatMessages = (chatId) => {
    return storage.getItem(getChatMessagesKey(chatId)) || [];
  };

  const saveChatMessages = (chatId, msgs) => {
    storage.setItem(getChatMessagesKey(chatId), msgs);
  };

  /* ---------- RESTORE HISTORY LIST ONLY ---------- */
  useEffect(() => {
    const storedHistory = storage.getItem('chatHistory');
    if (storedHistory && Array.isArray(storedHistory)) {
      const hydrated = storedHistory.map((entry) => ({
        ...entry,
        timestamp: entry.timestamp ? new Date(entry.timestamp) : new Date(),
        titleLocked:
          typeof entry.titleLocked === 'boolean'
            ? entry.titleLocked
            : entry.text !== 'New conversation'
      }));
      setHistory(hydrated);
    }
    setRestoring(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------- ALWAYS OPEN NEW CHAT ON LOGIN ---------- */
  useEffect(() => {
    if (!user?.id) return;

    const timestamp = new Date();
    const newChatId = timestamp.getTime();

    const newChat = {
      id: newChatId,
      text: 'New conversation',
      titleLocked: false,
      timestamp
    };

    setHistory((prev) => [newChat, ...prev]);
    setActiveHistoryId(newChatId);
    setMessages([]);
  }, [user]);

  /* ---------- PERSIST CURRENT CHAT ---------- */
  useEffect(() => {
    if (!restoring && activeHistoryId) {
      saveChatMessages(activeHistoryId, messages);
      storage.setItem('activeHistoryId', activeHistoryId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, activeHistoryId, restoring]);

  useEffect(() => {
    if (!restoring) {
      storage.setItem('chatHistory', history);
    }
  }, [history, restoring]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  /* ---------- UTILITIES ---------- */
  const pushNotification = useCallback((text) => {
    const id = Date.now();
    setNotifications((prev) => [...prev, { id, text }]);
    setTimeout(() => {
      setNotifications((prev) => prev.filter((n) => n.id !== id));
    }, 2000);
  }, []);

  const focusInput = useCallback(() => {
    inputRef.current?.focus();
  }, []);

  /* ---------- SEND MESSAGE ---------- */
  const handleSendMessage = async (text) => {
    const userMessage = {
      id: Date.now(),
      text,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages((prev) => [...prev, userMessage]);
    upsertHistoryItem(text, userMessage.timestamp);

    try {
      const data = await queryAgent(text);

      const botMessage = {
        id: Date.now() + 1,
        text: data.answer || 'No response from AgroGPT',
        sender: 'bot',
        timestamp: new Date()
      };

      setMessages((prev) => [...prev, botMessage]);

      if (user?.id) {
        try {
          await saveChat(user.id, text, botMessage.text);
        } catch {
          // ignore backend save failure
        }
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 2,
          text: '❌ Unable to reach AgroGPT backend.',
          sender: 'bot',
          timestamp: new Date()
        }
      ]);
    }
  };

  /* ---------- CHAT ACTIONS ---------- */
  const handleNewChat = useCallback(() => {
    const timestamp = new Date();
    const newId = timestamp.getTime();
    const placeholder = {
      id: newId,
      text: 'New conversation',
      titleLocked: false,
      timestamp
    };
    setHistory((prev) => [placeholder, ...prev]);
    setActiveHistoryId(newId);
    setMessages([]);
    setOpenMenuId(null);
    pushNotification('New chat created');
  }, [pushNotification]);

  const handleLoadChat = useCallback((chatId) => {
    setActiveHistoryId(chatId);
    const storedMessages = getChatMessages(chatId);
    if (storedMessages && Array.isArray(storedMessages)) {
      const hydrated = storedMessages.map((msg) => ({
        ...msg,
        timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
      }));
      setMessages(hydrated);
    } else {
      setMessages([]);
    }
    setOpenMenuId(null);
  }, []);

  const upsertHistoryItem = (text, timestamp = new Date()) => {
    setHistory((prev) => {
      if (activeHistoryId) {
        return prev.map((entry) => {
          if (entry.id !== activeHistoryId) return entry;
          if (entry.titleLocked) return { ...entry, timestamp };
          return { ...entry, text, timestamp, titleLocked: true };
        });
      }
      const newId = timestamp.getTime();
      setActiveHistoryId(newId);
      return [{ id: newId, text, timestamp, titleLocked: true }, ...prev];
    });
  };

  /* ---------- LOGOUT (NO AUTO RESTORE) ---------- */
  const handleLogout = () => {
    setMessages([]);
    setActiveHistoryId(null);
    storage.removeItem('activeHistoryId');
    logout();
    navigate('/login');
  };

  /* ---------- CLEAR HISTORY ---------- */
  const clearHistory = () => {
    setHistory([]);
    setMessages([]);
    setActiveHistoryId(null);
    storage.removeItem('chatHistory');
    storage.removeItem('activeHistoryId');
    setShowSettings(false);
  };

  /* ---------- SHORTCUTS ---------- */
  useEffect(() => {
    const handleShortcuts = (event) => {
      const key = event.key.toLowerCase();
      const isMeta = event.metaKey || event.ctrlKey;

      if (isMeta && key === 'n') {
        event.preventDefault();
        handleNewChat();
      } else if (event.key === '/') {
        event.preventDefault();
        focusInput();
      }
    };

    window.addEventListener('keydown', handleShortcuts);
    return () => window.removeEventListener('keydown', handleShortcuts);
  }, [focusInput, handleNewChat]);

  /* ---------- UI (UNCHANGED) ---------- */
  return (
    <div className="chatbot-container">
      <div className="chat-layout">
        <aside className="chat-sidebar">
          <div className="sidebar-header">
            <button className="new-chat-button" onClick={handleNewChat}>
              + New Chat
            </button>
          </div>

          <ChatHistory
            history={history}
            activeHistoryId={activeHistoryId}
            onHistorySelect={handleLoadChat}
            onHistoryClick={handleLoadChat}
            openMenuId={openMenuId}
          />

          <WeatherWidget location={location} />
        </aside>

        <div className="chat-main">
          <div className="chatbot-header">
            <div className="header-left">
              <FaUserCircle className="header-icon" />
              <div className="user-info">
                <span className="user-name">{user?.name || user?.email}</span>
                <span className="user-email">{user?.email}</span>
              </div>
            </div>

            <div className="header-right">
              <button className="theme-toggle" onClick={toggleTheme}>
                {theme === 'light' ? <FaMoon /> : <FaSun />}
              </button>
              <button onClick={() => setShowSettings(true)}>
                <FaCog />
              </button>
              <button className="logout-btn" onClick={handleLogout}>
                <FaSignOutAlt /> Logout
              </button>
            </div>
          </div>

          <SettingsModal
            isOpen={showSettings}
            onClose={() => setShowSettings(false)}
            onClearHistory={clearHistory}
          />

          <div className={`chatbot-content ${hasMessages ? '' : 'chatbot-content-empty'}`}>
            {hasMessages ? (
              <>
                <QuickActions onActionClick={handleSendMessage} />
                <MessageList messages={messages} />
                <div ref={endRef} />
              </>
            ) : (
              <div className="chat-empty-state">
                <h2>Start a farming conversation</h2>
                <p>Ask about weather, pests, crops, fertilizers, or market trends.</p>
                <QuickActions onActionClick={handleSendMessage} />
              </div>
            )}
          </div>

          <MessageInput
            onSendMessage={handleSendMessage}
            isCentered={!hasMessages}
            disabled={restoring}
            inputRef={inputRef}
          />
        </div>
      </div>

      {showHelp && <div className="help-overlay" />}

      <div className="toast-stack">
        {notifications.map((note) => (
          <div key={note.id} className="toast">
            {note.text}
          </div>
        ))}
      </div>
    </div>
  );
};

export default ChatBot;
