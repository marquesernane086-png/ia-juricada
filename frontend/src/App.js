import React, { useState } from "react";
import "@/App.css";
import ChatPage from "@/components/ChatPage";
import DocumentsPage from "@/components/DocumentsPage";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Badge } from "@/components/ui/badge";
import {
  Scale,
  MessageSquare,
  BookOpen,
  Menu,
  X,
} from "lucide-react";

function App() {
  const [activeTab, setActiveTab] = useState("chat");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const navItems = [
    { id: "chat", label: "Consulta", icon: MessageSquare },
    { id: "documents", label: "Acervo", icon: BookOpen },
  ];

  return (
    <div className="flex h-screen bg-background" data-testid="app-root">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:static inset-y-0 left-0 z-50 w-56 bg-card border-r flex flex-col transition-transform duration-200 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
        data-testid="sidebar"
      >
        {/* Logo */}
        <div className="p-4 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 flex items-center justify-center shadow-sm">
            <Scale className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-sm tracking-tight">JuristaAI</h1>
            <p className="text-[10px] text-muted-foreground">
              Doutrina Jurídica
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto md:hidden h-8 w-8"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        <Separator />

        {/* Navigation */}
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <Button
                key={item.id}
                variant={isActive ? "secondary" : "ghost"}
                className={`w-full justify-start gap-2.5 h-9 text-xs ${
                  isActive
                    ? "bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200 hover:bg-amber-100"
                    : ""
                }`}
                onClick={() => {
                  setActiveTab(item.id);
                  setSidebarOpen(false);
                }}
                data-testid={`nav-${item.id}`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Button>
            );
          })}
        </nav>

        {/* Footer info */}
        <div className="p-3 border-t">
          <div className="text-[10px] text-muted-foreground space-y-1">
            <p className="font-medium">Motor Doutrinário v1.0</p>
            <p>RAG + OpenAI GPT-4o-mini</p>
            <p>Embeddings: Multilingual MiniLM</p>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header className="md:hidden flex items-center gap-3 p-3 border-b">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => setSidebarOpen(true)}
            data-testid="mobile-menu"
          >
            <Menu className="w-4 h-4" />
          </Button>
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-amber-600" />
            <span className="text-sm font-bold">JuristaAI</span>
          </div>
          <Badge
            variant="outline"
            className="ml-auto text-[10px] cursor-pointer"
            onClick={() => setActiveTab(activeTab === "chat" ? "documents" : "chat")}
          >
            {activeTab === "chat" ? "Acervo" : "Consulta"}
          </Badge>
        </header>

        {/* Page content */}
        {activeTab === "chat" ? <ChatPage /> : <DocumentsPage />}
      </main>
    </div>
  );
}

export default App;
