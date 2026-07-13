import { Component, ElementRef, ViewChild, signal, AfterViewChecked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  time: string;
}

interface ChatResponse {
  status: string;
  response: string;
}

function timestamp(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// backend responses use **bold** for emphasis (e.g. ticket IDs) — render it, nothing else
function formatContent(text: string): string {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

@Component({
  selector: 'app-root',
  imports: [FormsModule],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App implements AfterViewChecked {
  @ViewChild('thread') private threadEl?: ElementRef<HTMLElement>;

  protected readonly userId = 'demo-user';
  protected readonly conversationId = this.loadConversationId();
  protected readonly sessionLabel = this.conversationId.slice(0, 6);

  protected readonly messages = signal<ChatMessage[]>([
    { role: 'assistant', content: 'Hello! How can I help you today?', time: timestamp() }
  ]);
  protected readonly draft = signal('');
  protected readonly sending = signal(false);
  protected readonly errorMessage = signal('');

  protected readonly formatContent = formatContent;

  private shouldScroll = false;

  constructor(private readonly http: HttpClient) {}

  ngAfterViewChecked(): void {
    if (this.shouldScroll && this.threadEl) {
      this.threadEl.nativeElement.scrollTop = this.threadEl.nativeElement.scrollHeight;
      this.shouldScroll = false;
    }
  }

  protected send(): void {
    const text = this.draft().trim();
    if (!text || this.sending()) return;

    this.errorMessage.set('');
    this.messages.update(msgs => [...msgs, { role: 'user', content: text, time: timestamp() }]);
    this.draft.set('');
    this.sending.set(true);
    this.shouldScroll = true;

    this.http.post<ChatResponse>('/chat', {
      user_id: this.userId,
      conversation_id: this.conversationId,
      message: text
    }).subscribe({
      next: res => {
        this.messages.update(msgs => [...msgs, { role: 'assistant', content: res.response, time: timestamp() }]);
        this.sending.set(false);
        this.shouldScroll = true;
      },
      error: () => {
        this.errorMessage.set("Couldn't reach the assistant. Check that the backend is running and try again.");
        this.sending.set(false);
        this.shouldScroll = true;
      }
    });
  }

  private loadConversationId(): string {
    const key = 'aiorc_conversation_id';
    let id = sessionStorage.getItem(key);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(key, id);
    }
    return id;
  }
}
