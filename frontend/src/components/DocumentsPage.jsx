import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import {
  Upload,
  FileText,
  Trash2,
  RefreshCw,
  BookOpen,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  AlertCircle,
  Search,
  Edit,
  PackageOpen,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Status badge component
const StatusBadge = ({ status }) => {
  const config = {
    indexed: {
      label: "Indexado",
      variant: "default",
      icon: CheckCircle2,
      className: "bg-emerald-600",
    },
    processing: {
      label: "Processando",
      variant: "secondary",
      icon: Loader2,
      className: "bg-blue-500",
    },
    pending: {
      label: "Pendente",
      variant: "secondary",
      icon: Clock,
      className: "bg-yellow-500",
    },
    error: {
      label: "Erro",
      variant: "destructive",
      icon: XCircle,
      className: "",
    },
    duplicate: {
      label: "Duplicado",
      variant: "outline",
      icon: AlertCircle,
      className: "",
    },
  };

  const cfg = config[status] || config.pending;
  const Icon = cfg.icon;

  return (
    <Badge variant={cfg.variant} className={`text-[10px] ${cfg.className}`}>
      <Icon
        className={`w-3 h-3 mr-1 ${status === "processing" ? "animate-spin" : ""}`}
      />
      {cfg.label}
    </Badge>
  );
};

// Document card
const DocumentCard = ({ doc, onDelete, onReindex, onEdit }) => {
  const [deleting, setDeleting] = useState(false);
  const [reindexing, setReindexing] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await onDelete(doc.id);
    } finally {
      setDeleting(false);
    }
  };

  const handleReindex = async () => {
    setReindexing(true);
    try {
      await onReindex(doc.id);
    } finally {
      setReindexing(false);
    }
  };

  return (
    <Card
      className="hover:shadow-md transition-shadow"
      data-testid={`document-card-${doc.id}`}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="w-10 h-10 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center flex-shrink-0">
              <BookOpen className="w-5 h-5 text-amber-600" />
            </div>
            <div className="min-w-0 flex-1">
              <h3
                className="font-medium text-sm truncate"
                title={doc.title || doc.file_name}
              >
                {doc.title || doc.file_name}
              </h3>
              {doc.author && (
                <p className="text-xs text-muted-foreground truncate">
                  {doc.author}
                </p>
              )}
              <div className="flex flex-wrap gap-1.5 mt-2">
                <StatusBadge status={doc.status} />
                {doc.year && (
                  <Badge variant="outline" className="text-[10px]">
                    {doc.year}
                  </Badge>
                )}
                {doc.total_chunks > 0 && (
                  <Badge variant="outline" className="text-[10px]">
                    {doc.total_chunks} trechos
                  </Badge>
                )}
                {doc.legal_subject && (
                  <Badge variant="outline" className="text-[10px]">
                    {doc.legal_subject}
                  </Badge>
                )}
                <Badge variant="outline" className="text-[10px] uppercase">
                  {doc.file_type}
                </Badge>
              </div>
              {doc.error_message && (
                <p className="text-xs text-destructive mt-1.5 truncate">
                  {doc.error_message}
                </p>
              )}
            </div>
          </div>
          <div className="flex gap-1 flex-shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => onEdit(doc)}
              title="Editar metadados"
              data-testid={`edit-doc-${doc.id}`}
            >
              <Edit className="w-3.5 h-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={handleReindex}
              disabled={reindexing || doc.status === "processing"}
              title="Reindexar"
              data-testid={`reindex-doc-${doc.id}`}
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${reindexing ? "animate-spin" : ""}`}
              />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive hover:text-destructive"
              onClick={handleDelete}
              disabled={deleting}
              title="Excluir"
              data-testid={`delete-doc-${doc.id}`}
            >
              {deleting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Trash2 className="w-3.5 h-3.5" />
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [editDoc, setEditDoc] = useState(null);
  const [editForm, setEditForm] = useState({});
  const fileInputRef = useRef(null);
  const importInputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  const fetchDocuments = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/documents`);
      setDocuments(res.data.documents || []);
    } catch (e) {
      console.error("Error fetching documents:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
    // Poll for status updates
    const interval = setInterval(fetchDocuments, 5000);
    return () => clearInterval(interval);
  }, [fetchDocuments]);

  const handleUpload = async (files) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    setUploadProgress(0);

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append("file", file);

      try {
        await axios.post(`${API}/documents/upload`, formData, {
          headers: { "Content-Type": "multipart/form-data" },
          onUploadProgress: (progressEvent) => {
            const total = files.length;
            const fileProgress = progressEvent.loaded / progressEvent.total;
            const overallProgress = ((i + fileProgress) / total) * 100;
            setUploadProgress(Math.round(overallProgress));
          },
        });
      } catch (e) {
        console.error(`Error uploading ${file.name}:`, e);
      }
    }

    setUploading(false);
    setUploadProgress(0);
    fetchDocuments();
  };

  const handleFileSelect = (e) => {
    handleUpload(e.target.files);
    e.target.value = "";
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (f) => f.name.endsWith(".pdf") || f.name.endsWith(".epub")
    );
    if (files.length > 0) handleUpload(files);
  };

  const handleDelete = async (docId) => {
    try {
      await axios.delete(`${API}/documents/${docId}`);
      fetchDocuments();
    } catch (e) {
      console.error("Error deleting document:", e);
    }
  };

  const handleReindex = async (docId) => {
    try {
      await axios.post(`${API}/documents/${docId}/reindex`);
      fetchDocuments();
    } catch (e) {
      console.error("Error reindexing document:", e);
    }
  };

  const handleEdit = (doc) => {
    setEditDoc(doc);
    setEditForm({
      title: doc.title || "",
      author: doc.author || "",
      year: doc.year || "",
      edition: doc.edition || "",
      legal_subject: doc.legal_subject || "",
      legal_institute: doc.legal_institute || "",
    });
  };

  const handleSaveEdit = async () => {
    if (!editDoc) return;
    try {
      const payload = { ...editForm };
      if (payload.year) payload.year = parseInt(payload.year);
      else delete payload.year;

      await axios.patch(`${API}/documents/${editDoc.id}`, payload);
      setEditDoc(null);
      fetchDocuments();
    } catch (e) {
      console.error("Error updating document:", e);
    }
  };

  const filteredDocs = documents.filter((doc) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      (doc.title || "").toLowerCase().includes(q) ||
      (doc.author || "").toLowerCase().includes(q) ||
      (doc.legal_subject || "").toLowerCase().includes(q) ||
      (doc.file_name || "").toLowerCase().includes(q)
    );
  });

  return (
    <div className="flex flex-col h-full" data-testid="documents-page">
      <div className="p-4 space-y-4 flex-1 overflow-auto custom-scrollbar">
        {/* Upload area */}
        <div
          className={`upload-dropzone border-2 border-dashed rounded-xl p-6 text-center transition-all cursor-pointer ${
            dragOver
              ? "drag-over border-amber-500 bg-amber-50 dark:bg-amber-950/20"
              : "border-border hover:border-amber-300"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          data-testid="upload-dropzone"
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.epub"
            multiple
            onChange={handleFileSelect}
            data-testid="file-input"
          />
          <Upload className="w-8 h-8 mx-auto mb-2 text-muted-foreground" />
          <p className="text-sm font-medium">
            Arraste livros jurídicos aqui ou clique para selecionar
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Formatos aceitos: PDF, EPUB
          </p>
          {uploading && (
            <div className="mt-3 max-w-xs mx-auto">
              <Progress value={uploadProgress} className="h-2" />
              <p className="text-xs text-muted-foreground mt-1">
                Enviando... {uploadProgress}%
              </p>
            </div>
          )}
        </div>

        {/* Search and count */}
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por título, autor ou matéria..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-9"
              data-testid="search-input"
            />
          </div>
          <Badge variant="secondary" className="text-xs whitespace-nowrap">
            {filteredDocs.length} documento(s)
          </Badge>
        </div>

        {/* Document list */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : filteredDocs.length === 0 ? (
          <div className="text-center py-12">
            <BookOpen className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              {searchQuery
                ? "Nenhum documento encontrado."
                : "Nenhum livro jurídico adicionado. Faça upload para começar."}
            </p>
          </div>
        ) : (
          <div className="grid gap-2">
            {filteredDocs.map((doc) => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                onDelete={handleDelete}
                onReindex={handleReindex}
                onEdit={handleEdit}
              />
            ))}
          </div>
        )}
      </div>

      {/* Edit dialog */}
      <Dialog
        open={!!editDoc}
        onOpenChange={(open) => !open && setEditDoc(null)}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Editar Metadados</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div>
              <Label className="text-xs">Título</Label>
              <Input
                value={editForm.title || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, title: e.target.value })
                }
                className="h-9 mt-1"
                data-testid="edit-title"
              />
            </div>
            <div>
              <Label className="text-xs">Autor</Label>
              <Input
                value={editForm.author || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, author: e.target.value })
                }
                className="h-9 mt-1"
                data-testid="edit-author"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Ano</Label>
                <Input
                  type="number"
                  value={editForm.year || ""}
                  onChange={(e) =>
                    setEditForm({ ...editForm, year: e.target.value })
                  }
                  className="h-9 mt-1"
                  data-testid="edit-year"
                />
              </div>
              <div>
                <Label className="text-xs">Edição</Label>
                <Input
                  value={editForm.edition || ""}
                  onChange={(e) =>
                    setEditForm({ ...editForm, edition: e.target.value })
                  }
                  className="h-9 mt-1"
                  data-testid="edit-edition"
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Matéria Jurídica</Label>
              <Input
                value={editForm.legal_subject || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, legal_subject: e.target.value })
                }
                placeholder="Ex: Direito Civil, Penal, Constitucional..."
                className="h-9 mt-1"
                data-testid="edit-legal-subject"
              />
            </div>
            <div>
              <Label className="text-xs">Instituto Jurídico</Label>
              <Input
                value={editForm.legal_institute || ""}
                onChange={(e) =>
                  setEditForm({ ...editForm, legal_institute: e.target.value })
                }
                placeholder="Ex: Responsabilidade Civil, Contrato..."
                className="h-9 mt-1"
                data-testid="edit-legal-institute"
              />
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline" size="sm">
                Cancelar
              </Button>
            </DialogClose>
            <Button
              size="sm"
              className="bg-amber-600 hover:bg-amber-700"
              onClick={handleSaveEdit}
              data-testid="save-edit-button"
            >
              Salvar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
