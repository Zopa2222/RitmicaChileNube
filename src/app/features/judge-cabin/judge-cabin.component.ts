import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';

import { JudgeContext } from '../../core/models/cloud.model';
import { JudgeCabinApiService } from '../../core/services/judge-cabin-api.service';

interface LocalDraft { activationId: string; value: string; savedAt: string; }

@Component({
    selector: 'app-judge-cabin',
    standalone: true,
    imports: [CommonModule, FormsModule, MatButtonModule, MatIconModule],
    templateUrl: './judge-cabin.component.html',
    styleUrls: ['./judge-cabin.component.scss']
})
export class JudgeCabinComponent implements OnInit, OnDestroy {
    contexts: JudgeContext[] = [];
    values: Record<string, string> = {};
    statuses: Record<string, string> = {};
    loading = true;
    serverTime = '';
    private refreshTimer: number | null = null;
    private readonly onlineHandler = () => void this.retryLocalDrafts();

    constructor(private readonly cabinApi: JudgeCabinApiService) { }

    ngOnInit(): void {
        void this.load();
        this.refreshTimer = window.setInterval(() => void this.load(), 10000);
        window.addEventListener('online', this.onlineHandler);
    }

    ngOnDestroy(): void {
        if (this.refreshTimer !== null) window.clearInterval(this.refreshTimer);
        window.removeEventListener('online', this.onlineHandler);
    }

    async load(): Promise<void> {
        try {
            const response = await firstValueFrom(this.cabinApi.getContexts());
            this.contexts = response.contexts;
            this.serverTime = response.serverTime;
            for (const context of this.contexts) {
                const score = context.active?.score;
                if (score && this.values[score.id] === undefined) this.values[score.id] = score.value;
            }
            await this.retryLocalDrafts();
        } catch {
            this.statuses.global = 'Sin conexión con el servidor. Conservaremos el último borrador.';
        } finally { this.loading = false; }
    }

    async save(context: JudgeContext): Promise<void> {
        const score = context.active?.score;
        const activationId = context.active?.activation_id;
        if (!score || !activationId || !context.can_score) return;
        const value = this.values[score.id];
        try {
            const response = await firstValueFrom(this.cabinApi.updateScore(score.id, activationId, value));
            this.removeDraft(score.id);
            this.values[score.id] = response.score.value;
            this.statuses[score.id] = `Guardado · ${new Date(response.server_time).toLocaleTimeString('es-CL')}`;
        } catch (error: any) {
            this.persistDraft(score.id, { activationId, value, savedAt: new Date().toISOString() });
            const stale = error?.error?.code === 'STALE_ACTIVATION';
            this.statuses[score.id] = stale
                ? 'La rutina cambió: el borrador no se enviará a otra gimnasta.'
                : 'Pendiente de sincronización. Se reintentará al recuperar conexión.';
        }
    }

    async retryLocalDrafts(): Promise<void> {
        for (const context of this.contexts) {
            const score = context.active?.score;
            const activationId = context.active?.activation_id;
            if (!score || !activationId || !context.can_score) continue;
            const draft = this.readDraft(score.id);
            if (!draft) continue;
            if (draft.activationId !== activationId) {
                this.statuses[score.id] = 'Borrador descartado: corresponde a una activación anterior.';
                this.removeDraft(score.id);
                continue;
            }
            this.values[score.id] = draft.value;
            await this.save(context);
        }
    }

    private key(scoreId: string): string { return `ritmica-judge-draft:${scoreId}`; }
    private persistDraft(scoreId: string, draft: LocalDraft): void { localStorage.setItem(this.key(scoreId), JSON.stringify(draft)); }
    private readDraft(scoreId: string): LocalDraft | null {
        try { return JSON.parse(localStorage.getItem(this.key(scoreId)) ?? 'null') as LocalDraft | null; } catch { return null; }
    }
    private removeDraft(scoreId: string): void { localStorage.removeItem(this.key(scoreId)); }
}
