import React, { useState, useRef, useEffect, useCallback } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Send,
  BookOpen,
  Scale,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  Loader2,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Loading dots component
const LoadingDots = () => (
  <div className="flex items-center gap-1.5 px-4 py-3">
    <Scale className="w-4 h-4 text-amber-600 mr-2" />
    <span className="text-sm text-muted-foreground mr-2">
      Analisando doutrina...
    </span>
    <div className="loading-dot w-2 h-2 bg-amber-600 rounded-full"></div>
    <div className="loading-dot w-2 h-2 bg-amber-600 rounded-full"></div>
    <div className="loading-dot w-2 h-2 bg-amber-600 rounded-full"></div>
  </div>
);

// Source reference component
const SourceCard = ({ source, index }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <button
          data-testid={`source-trigger-${index}`}
          className="w-full flex items-center justify-between p-2 rounded-md hover:bg-muted/50 transition-colors text-left"
        >
          <div className="flex items-center gap-2 min-w-0">
            <FileText className="w-3.5 h-3.5 text-amber-600 flex-shrink-0" />
            <span className="text-xs font-medium truncate">
              {source.author || "Autor desconhecido"}
            </span>
            {source.year && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 flex-shrink-0">
                {source.year}
              </Badge>
            )}
          </div>
          {isOpen ? (
            <ChevronUp className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 flex-shrink-0 text-muted-foreground" />
          )}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="px-2 pb-2 text-xs text-muted-foreground">
          <p className="font-medium text-foreground mb-1">
            {source.title}
          </p>
          <p className="italic leading-relaxed">{source.chunk_text}</p>
          <div className="flex gap-2 mt-1.5">
            <Badge variant="secondary" className="text-[10px]">
              Relevância: {(source.relevance_score * 100).toFixed(0)}%
            </Badge>
            {source.page && (
              <Badge variant="secondary" className="text-[10px]">
                Pág. {source.page}
              </Badge>
            )}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
};

// Chat message component
const ChatMessage = ({ message }) => {
  const isUser = message.role === "user";
  const [sourcesOpen, setSourcesOpen] = useState(false);

  return (
    <div
      className={`animate-fade-in-up flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
      data-testid={`chat-message-${message.role}`}
    >
      <div
        className={`max-w-[85%] ${
          isUser
            ? "bg-primary text-primary-foreground rounded-2xl rounded-br-md px-4 py-3"
            : "bg-card border rounded-2xl rounded-bl-md px-5 py-4 shadow-sm"
        }`}
      >
        {isUser ? (
          <p className="text-sm leading-relaxed">{message.content}</p>
        ) : (
          <div>
            <div className="prose text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>

            {/* Sources */}
            {message.sources && message.sources.length > 0 && (
              <Collapsible
                open={sourcesOpen}
                onOpenChange={setSourcesOpen}
                className="mt-4"
              >
                <CollapsibleTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-between text-xs h-8"
                    data-testid="sources-toggle"
                  >
                    <span className="flex items-center gap-1.5">
                      <BookOpen className="w-3.5 h-3.5" />
                      {message.sources.length} fonte(s) doutrinária(s)
                    </span>
                    {sourcesOpen ? (
                      <ChevronUp className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5" />
                    )}
                  </Button>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="mt-2 space-y-1 border rounded-lg p-2 bg-muted/30">
                    {message.sources.map((source, idx) => (
                      <SourceCard key={idx} source={source} index={idx} />
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            )}

            {/* Processing info */}
            {message.processing_time && (
              <div className="flex items-center gap-1.5 mt-3 text-[10px] text-muted-foreground">
                <Clock className="w-3 h-3" />
                <span>
                  {message.processing_time}s · {message.chunks_retrieved || 0}{" "}
                  trechos consultados
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [stats, setStats] = useState(null);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);
  const sessionId = useRef(crypto.randomUUID());

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading, scrollToBottom]);

  // Fetch stats on mount
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await axios.get(`${API}/chat/stats`);
        setStats(res.data);
      } catch (e) {
        console.error("Error fetching stats:", e);
      }
    };
    fetchStats();
  }, []);

  const handleSend = async () => {
    const question = input.trim();
    if (!question || isLoading) return;

    // Add user message
    const userMessage = { role: "user", content: question };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await axios.post(`${API}/chat`, {
        question,
        session_id: sessionId.current,
        max_sources: 15,
      }, {
        timeout: 120000, // 2 minutos de timeout
      });

      const data = response.data;
      const assistantMessage = {
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        processing_time: data.processing_time,
        chunks_retrieved: data.chunks_retrieved,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error:", error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "Erro ao processar sua consulta. Verifique se o servidor está ativo e tente novamente.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const suggestedQuestions = [
    "O que é responsabilidade civil objetiva?",
    "Qual a diferença entre dolo e culpa no direito penal?",
    "Explique o princípio da dignidade da pessoa humana.",
    "O que são direitos reais de garantia?",
  ];

  return (
    <div className="flex flex-col h-full" data-testid="chat-page">
      {/* Messages area */}
      <ScrollArea className="flex-1 px-4 py-4 custom-scrollbar">
        {messages.length === 0 ? (
          /* Welcome screen */
          <div className="flex flex-col items-center justify-center h-full min-h-[60vh] text-center px-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center mb-6 shadow-lg">
              <Scale className="w-8 h-8 text-white" />
            </div>
            <h2 className="text-2xl font-bold mb-2" data-testid="welcome-title">
              JuristaAI
            </h2>
            <p className="text-muted-foreground mb-6 max-w-md">
              Assistente jurídico doutrinário avançado. Faça perguntas sobre
              direito brasileiro e receba respostas fundamentadas com citações
              doutrinárias.
            </p>

            {stats && (stats.indexed_documents > 0 || stats.total_chunks > 0) && (
              <div className="flex gap-3 mb-6">
                {stats.indexed_documents > 0 && (
                  <Badge variant="secondary" className="text-xs">
                    <BookOpen className="w-3 h-3 mr-1" />
                    {stats.indexed_documents} obra(s) indexada(s)
                  </Badge>
                )}
                <Badge variant="secondary" className="text-xs">
                  <FileText className="w-3 h-3 mr-1" />
                  {stats.total_chunks.toLocaleString()} trechos indexados
                </Badge>
              </div>
            )}

            {stats && stats.indexed_documents === 0 && stats.total_chunks === 0 && (
              <Card className="mb-6 max-w-md border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-800">
                <CardContent className="p-4 text-sm text-amber-800 dark:text-amber-200">
                  <p className="font-medium mb-1">📚 Nenhum livro indexado</p>
                  <p className="text-xs">
                    Para obter respostas doutrinárias fundamentadas, faça upload
                    de livros jurídicos na aba "Acervo".
                  </p>
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg w-full">
              {suggestedQuestions.map((q, idx) => (
                <Button
                  key={idx}
                  variant="outline"
                  size="sm"
                  className="text-xs text-left h-auto py-2.5 px-3 justify-start hover:bg-amber-50 dark:hover:bg-amber-950/20 hover:border-amber-300"
                  onClick={() => setInput(q)}
                  data-testid={`suggested-question-${idx}`}
                >
                  <Scale className="w-3 h-3 mr-2 flex-shrink-0 text-amber-600" />
                  <span className="line-clamp-2">{q}</span>
                </Button>
              ))}
            </div>
          </div>
        ) : (
          /* Messages */
          <div className="max-w-3xl mx-auto">
            {messages.map((msg, idx) => (
              <ChatMessage key={idx} message={msg} />
            ))}
            {isLoading && (
              <div className="flex justify-start mb-4">
                <div className="bg-card border rounded-2xl rounded-bl-md shadow-sm">
                  <LoadingDots />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}
      </ScrollArea>

      {/* Input area */}
      <div className="border-t bg-background p-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Faça uma pergunta jurídica doutrinária..."
            className="min-h-[44px] max-h-[120px] resize-none"
            rows={1}
            disabled={isLoading}
            data-testid="chat-input"
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            size="icon"
            className="h-[44px] w-[44px] flex-shrink-0 bg-amber-600 hover:bg-amber-700"
            data-testid="send-button"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
