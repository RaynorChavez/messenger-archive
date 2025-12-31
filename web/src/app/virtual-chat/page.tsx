"use client";

import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { AppLayout } from "@/components/layout/app-layout";
import { Loader2, MessageCircle, Plus, Send, User, X, Check, Search } from "lucide-react";
import {
  people,
  virtualChat,
  mxcToHttp,
  PersonFull,
  VirtualParticipant,
  VirtualMessage,
  VirtualChatSSEEvent,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import katex from "katex";
import "katex/dist/katex.min.css";

// Render text with LaTeX math support
function renderMathText(text: string): React.ReactNode {
  if (!text) return null;
  
  // Split by $$...$$ (block) and $...$ (inline)
  const parts = text.split(/(\$\$[\s\S]+?\$\$|\$[^$]+?\$)/g);
  
  return parts.map((part, i) => {
    if (part.startsWith("$$") && part.endsWith("$$")) {
      // Block math
      const math = part.slice(2, -2);
      try {
        const html = katex.renderToString(math, { displayMode: true, throwOnError: false });
        return <div key={i} dangerouslySetInnerHTML={{ __html: html }} className="my-2 overflow-x-auto" />;
      } catch {
        return <span key={i}>{part}</span>;
      }
    } else if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
      // Inline math
      const math = part.slice(1, -1);
      try {
        const html = katex.renderToString(math, { displayMode: false, throwOnError: false });
        return <span key={i} dangerouslySetInnerHTML={{ __html: html }} />;
      } catch {
        return <span key={i}>{part}</span>;
      }
    }
    return <span key={i}>{part}</span>;
  });
}

interface AgentState {
  personId: number;
  displayName: string;
  avatarUrl: string | null;
  thinking: boolean;
  content: string;
  done: boolean;
}

interface ChatMessage {
  id: number;
  senderType: "user" | "agent";
  personId: number | null;
  displayName: string | null;
  avatarUrl: string | null;
  content: string;
}

function VirtualChatContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const conversationIdParam = searchParams.get("id");
  
  // State
  const [conversationId, setConversationId] = useState<number | null>(
    conversationIdParam ? parseInt(conversationIdParam) : null
  );
  const [participants, setParticipants] = useState<VirtualParticipant[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentStates, setAgentStates] = useState<Map<number, AgentState>>(new Map());
  const [inputValue, setInputValue] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  
  // Participant selector state
  const [allPeople, setAllPeople] = useState<PersonFull[]>([]);
  const [selectedPeople, setSelectedPeople] = useState<PersonFull[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  
  // Mention autocomplete state
  const [mentionQuery, setMentionQuery] = useState<string | null>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [cursorPosition, setCursorPosition] = useState(0);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const selectorRef = useRef<HTMLDivElement>(null);
  
  // Load all people for selector
  useEffect(() => {
    people.list().then((res) => setAllPeople(res.people));
  }, []);
  
  // Load existing conversation if ID provided
  useEffect(() => {
    if (conversationIdParam) {
      const id = parseInt(conversationIdParam);
      setIsLoading(true);
      virtualChat.getConversation(id)
        .then((conv) => {
          setConversationId(conv.id);
          setParticipants(conv.participants);
          setMessages(
            conv.messages.map((m) => ({
              id: m.id,
              senderType: m.sender_type,
              personId: m.person_id,
              displayName: m.person_display_name,
              avatarUrl: m.person_avatar_url,
              content: m.content,
            }))
          );
        })
        .finally(() => setIsLoading(false));
    }
  }, [conversationIdParam]);
  
  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, agentStates]);
  
  // Close selector when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (selectorRef.current && !selectorRef.current.contains(e.target as Node)) {
        setSelectorOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  
  // Create conversation with selected people
  const createConversation = async () => {
    if (selectedPeople.length === 0) return;
    
    setIsLoading(true);
    try {
      const conv = await virtualChat.createConversation(
        selectedPeople.map((p) => p.id)
      );
      setConversationId(conv.id);
      setParticipants(conv.participants);
      router.push(`/virtual-chat?id=${conv.id}`);
    } finally {
      setIsLoading(false);
    }
  };
  
  // Handle input change for mention detection
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    const cursor = e.target.selectionStart || 0;
    setInputValue(value);
    setCursorPosition(cursor);
    
    // Check for @ mention
    const textBeforeCursor = value.slice(0, cursor);
    const mentionMatch = textBeforeCursor.match(/@(\w*)$/);
    
    if (mentionMatch) {
      setMentionQuery(mentionMatch[1].toLowerCase());
      setMentionOpen(true);
    } else {
      setMentionQuery(null);
      setMentionOpen(false);
    }
  };
  
  // Insert mention
  const insertMention = (person: VirtualParticipant) => {
    const textBeforeCursor = inputValue.slice(0, cursorPosition);
    const textAfterCursor = inputValue.slice(cursorPosition);
    const mentionStart = textBeforeCursor.lastIndexOf("@");
    
    const newText =
      textBeforeCursor.slice(0, mentionStart) +
      `@${person.display_name} ` +
      textAfterCursor;
    
    setInputValue(newText);
    setMentionOpen(false);
    setMentionQuery(null);
    inputRef.current?.focus();
  };
  
  // Filter participants for mention autocomplete
  const filteredParticipants = participants.filter(
    (p) =>
      mentionQuery === null ||
      mentionQuery === "" ||
      p.display_name?.toLowerCase().includes(mentionQuery)
  );
  
  // Filter people for selector
  const filteredPeople = allPeople
    .filter(
      (p) =>
        !selectedPeople.some((sp) => sp.id === p.id) &&
        (searchQuery === "" ||
          p.display_name?.toLowerCase().includes(searchQuery.toLowerCase()))
    )
    .slice(0, 10);
  
  // Send message
  const sendMessage = async () => {
    if (!conversationId || !inputValue.trim() || isSending) return;
    
    const content = inputValue.trim();
    setInputValue("");
    setIsSending(true);
    setAgentStates(new Map());
    
    try {
      const response = await fetch(virtualChat.sendMessageUrl(conversationId), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");
      
      const decoder = new TextDecoder();
      let buffer = "";
      const newAgentStates = new Map<number, AgentState>();
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";
        
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          
          try {
            const event: VirtualChatSSEEvent = JSON.parse(line.slice(6));
            
            switch (event.type) {
              case "user_message":
                setMessages((prev) => [
                  ...prev,
                  {
                    id: event.id,
                    senderType: "user",
                    personId: null,
                    displayName: null,
                    avatarUrl: null,
                    content: event.content,
                  },
                ]);
                break;
                
              case "thinking":
                newAgentStates.set(event.person_id, {
                  personId: event.person_id,
                  displayName: event.display_name,
                  avatarUrl: participants.find((p) => p.person_id === event.person_id)?.avatar_url || null,
                  thinking: true,
                  content: "",
                  done: false,
                });
                setAgentStates(new Map(newAgentStates));
                break;
                
              case "chunk":
                const state = newAgentStates.get(event.person_id);
                if (state) {
                  state.thinking = false;
                  state.content += event.text;
                  setAgentStates(new Map(newAgentStates));
                }
                break;
                
              case "agent_done":
                const doneState = newAgentStates.get(event.person_id);
                if (doneState) {
                  doneState.done = true;
                  doneState.thinking = false;
                  
                  // Add to messages if there's content and it's not [NO RESPONSE]
                  const content = doneState.content.trim();
                  if (content && content !== "[NO RESPONSE]" && event.message_id) {
                    setMessages((prev) => [
                      ...prev,
                      {
                        id: event.message_id!,
                        senderType: "agent",
                        personId: doneState.personId,
                        displayName: doneState.displayName,
                        avatarUrl: doneState.avatarUrl,
                        content: content,
                      },
                    ]);
                  }
                  
                  // Remove from agent states
                  newAgentStates.delete(event.person_id);
                  setAgentStates(new Map(newAgentStates));
                }
                break;
                
              case "error":
                console.error("SSE Error:", event.message);
                break;
            }
          } catch (e) {
            console.error("Failed to parse SSE event:", e);
          }
        }
      }
    } catch (error) {
      console.error("Error sending message:", error);
    } finally {
      setIsSending(false);
    }
  };
  
  // Handle enter key
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !mentionOpen) {
      e.preventDefault();
      sendMessage();
    }
  };
  
  // Avatar component
  const Avatar = ({ src, name, className }: { src: string | null; name: string | null; className?: string }) => (
    <div className={cn("rounded-full bg-muted flex items-center justify-center overflow-hidden", className)}>
      {src ? (
        <img src={src} alt={name || "Avatar"} className="w-full h-full object-cover" />
      ) : (
        <span className="text-muted-foreground font-medium">{name?.[0] || "?"}</span>
      )}
    </div>
  );
  
  // Render participant selector (when no conversation yet)
  if (!conversationId) {
    return (
      <AppLayout>
        <div className="max-w-2xl mx-auto p-6">
          <div className="rounded-xl border bg-card p-6 space-y-4">
            <div className="flex items-center gap-2">
              <MessageCircle className="h-5 w-5" />
              <h1 className="text-xl font-semibold">Start Virtual Chat</h1>
            </div>
            
            <p className="text-muted-foreground text-sm">
              Select people to chat with. AI agents will roleplay as them based on their
              archived messages and communication style.
            </p>
            
            {/* Selected people */}
            <div className="flex flex-wrap gap-2">
              {selectedPeople.map((person) => (
                <span
                  key={person.id}
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-muted text-sm"
                >
                  <Avatar
                    src={mxcToHttp(person.avatar_url)}
                    name={person.display_name}
                    className="h-5 w-5 text-[10px]"
                  />
                  {person.display_name}
                  <button
                    onClick={() => setSelectedPeople((prev) => prev.filter((p) => p.id !== person.id))}
                    className="hover:text-destructive"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </span>
              ))}
            </div>
            
            {/* People selector */}
            <div className="relative" ref={selectorRef}>
              <button
                onClick={() => setSelectorOpen(!selectorOpen)}
                className="w-full flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-muted/50 text-sm text-muted-foreground"
              >
                <Plus className="h-4 w-4" />
                Add participants...
              </button>
              
              {selectorOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-popover border rounded-lg shadow-lg z-10 overflow-hidden">
                  <div className="p-2 border-b">
                    <div className="flex items-center gap-2 px-2">
                      <Search className="h-4 w-4 text-muted-foreground" />
                      <input
                        type="text"
                        placeholder="Search people..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="flex-1 bg-transparent outline-none text-sm"
                        autoFocus
                      />
                    </div>
                  </div>
                  <div className="max-h-64 overflow-y-auto">
                    {filteredPeople.length === 0 ? (
                      <div className="px-4 py-3 text-sm text-muted-foreground">
                        No people found.
                      </div>
                    ) : (
                      filteredPeople.map((person) => (
                        <button
                          key={person.id}
                          onClick={() => {
                            setSelectedPeople((prev) => [...prev, person]);
                            setSearchQuery("");
                          }}
                          className="w-full flex items-center gap-3 px-4 py-2 hover:bg-muted text-left"
                        >
                          <Avatar
                            src={mxcToHttp(person.avatar_url)}
                            name={person.display_name}
                            className="h-8 w-8 text-xs"
                          />
                          <span className="flex-1 text-sm">{person.display_name}</span>
                          <span className="text-xs text-muted-foreground">
                            {person.message_count} msgs
                          </span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
            
            {/* Start button */}
            <button
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={selectedPeople.length === 0 || isLoading}
              onClick={createConversation}
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <MessageCircle className="h-4 w-4" />
                  Start Chat with {selectedPeople.length} {selectedPeople.length === 1 ? "Person" : "People"}
                </>
              )}
            </button>
          </div>
        </div>
      </AppLayout>
    );
  }
  
  // Render chat interface
  return (
    <AppLayout>
      <div className="flex flex-col h-[calc(100vh-4rem)]">
        {/* Header */}
        <div className="border-b p-4">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-5 w-5" />
            <h1 className="font-semibold">Virtual Chat</h1>
            <div className="flex gap-1 ml-4">
              {participants.map((p) => (
                <Avatar
                  key={p.person_id}
                  src={mxcToHttp(p.avatar_url)}
                  name={p.display_name}
                  className="h-6 w-6 text-xs"
                />
              ))}
            </div>
            <span className="text-sm text-muted-foreground">
              {participants.map((p) => p.display_name).join(", ")}
            </span>
          </div>
        </div>
        
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground py-8">
              <MessageCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>Start a conversation!</p>
              <p className="text-sm mt-1">
                Type a message below. Use @name to mention someone.
              </p>
            </div>
          )}
          
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={cn(
                "flex gap-3",
                msg.senderType === "user" ? "justify-end" : "justify-start"
              )}
            >
              {msg.senderType === "agent" && (
                <Avatar
                  src={mxcToHttp(msg.avatarUrl)}
                  name={msg.displayName}
                  className="h-8 w-8 text-sm"
                />
              )}
              <div
                className={cn(
                  "max-w-[70%] rounded-lg px-4 py-2",
                  msg.senderType === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                )}
              >
                {msg.senderType === "agent" && (
                  <div className="text-xs font-medium mb-1">{msg.displayName}</div>
                )}
                <div className="text-sm whitespace-pre-wrap">{renderMathText(msg.content)}</div>
              </div>
              {msg.senderType === "user" && (
                <div className="h-8 w-8 rounded-full bg-muted flex items-center justify-center">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          ))}
          
          {/* Agent thinking/streaming indicators */}
          {Array.from(agentStates.values()).map((state) => (
            <div key={state.personId} className="flex gap-3 justify-start">
              <Avatar
                src={mxcToHttp(state.avatarUrl)}
                name={state.displayName}
                className="h-8 w-8 text-sm"
              />
              <div className="max-w-[70%] rounded-lg px-4 py-2 bg-muted">
                <div className="text-xs font-medium mb-1">{state.displayName}</div>
                {state.thinking ? (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    thinking...
                  </div>
                ) : (
                  <div className="text-sm whitespace-pre-wrap">
                    {renderMathText(state.content)}
                    <span className="inline-block w-1 h-4 bg-foreground/50 animate-pulse ml-0.5" />
                  </div>
                )}
              </div>
            </div>
          ))}
          
          <div ref={messagesEndRef} />
        </div>
        
        {/* Input */}
        <div className="border-t p-4">
          <div className="relative">
            {/* Mention autocomplete */}
            {mentionOpen && filteredParticipants.length > 0 && (
              <div className="absolute bottom-full left-0 mb-2 w-64 bg-popover border rounded-lg shadow-lg overflow-hidden">
                {filteredParticipants.map((p) => (
                  <button
                    key={p.person_id}
                    className="w-full px-3 py-2 text-left hover:bg-muted flex items-center gap-2"
                    onClick={() => insertMention(p)}
                  >
                    <Avatar
                      src={mxcToHttp(p.avatar_url)}
                      name={p.display_name}
                      className="h-5 w-5 text-xs"
                    />
                    <span className="text-sm">{p.display_name}</span>
                  </button>
                ))}
              </div>
            )}
            
            <div className="flex gap-2">
              <input
                ref={inputRef}
                type="text"
                placeholder={`Message ${participants.map((p) => p.display_name).join(", ")}... (use @ to mention)`}
                value={inputValue}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                disabled={isSending}
                className="flex-1 px-4 py-2 border rounded-lg bg-background outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              />
              <button
                onClick={sendMessage}
                disabled={!inputValue.trim() || isSending}
                className="px-4 py-2 rounded-lg bg-primary text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isSending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}

export default function VirtualChatPage() {
  return (
    <Suspense
      fallback={
        <AppLayout>
          <div className="flex items-center justify-center h-[calc(100vh-4rem)]">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        </AppLayout>
      }
    >
      <VirtualChatContent />
    </Suspense>
  );
}
