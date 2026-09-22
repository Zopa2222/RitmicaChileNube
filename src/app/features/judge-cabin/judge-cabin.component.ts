import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';

import { JudgeContext } from '../../core/models/cloud.model';
import { JudgeCabinApiService } from '../../core/services/judge-cabin-api.service';

interface LocalDraft { activationId: string; value: string; savedAt: string; }

const SCORE_MAX = 20;
const SCORE_RANGE_MESSAGE = 'La nota debe estar entre 0.00 y 20.00.';

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
    private editingScoreId: string | null = null;
    private readonly onlineHandler = () => void this.retryLocalDrafts();

    constructor(private readonly cabinApi: JudgeCabinApiService) { }

    ngOnInit(): void {
        void this.load();
        this.refreshTimer = window.setInterval(() => {
            void this.load();
        }, 10000);
        window.addEventListener('online', this.onlineHandler);
    }

    ngOnDestroy(): void {
        if (this.refreshTimer !== null) window.clearInterval(this.refreshTimer);
        window.removeEventListener('online', this.onlineHandler);
    }

    async load(): Promise<void> {
        try {
            const response = await firstValueFrom(this.cabinApi.getContexts());
            // Do not replace the view while a judge is using the mobile keyboard.
            // A request already in flight must not steal focus either.
            if (this.editingScoreId) return;
            this.contexts = response.contexts;
            this.serverTime = response.serverTime;
            for (const context of this.contexts) {
                const score = context.active?.score;
                if (!score) continue;
                if (this.values[score.id] === undefined) {
                    this.values[score.id] = this.formatScoreValue(score.value);
                }
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
        if (
            this.statuses[score.id] === SCORE_RANGE_MESSAGE
            || !this.isCompleteScoreValue(value)
        ) {
            this.statuses[score.id] = SCORE_RANGE_MESSAGE;
            this.removeDraft(score.id);
            return;
        }
        try {
            const response = await firstValueFrom(this.cabinApi.updateScore(score.id, activationId, value));
            this.removeDraft(score.id);
            this.values[score.id] = this.formatScoreValue(response.score.value);
            this.statuses[score.id] = `Guardado · ${new Date(response.server_time).toLocaleTimeString('es-CL')}`;
        } catch (error: any) {
            if (error?.error?.code === 'INVALID_SCORE') {
                this.removeDraft(score.id);
                this.statuses[score.id] = error?.error?.error ?? SCORE_RANGE_MESSAGE;
                return;
            }
            this.persistDraft(score.id, { activationId, value, savedAt: new Date().toISOString() });
            const stale = error?.error?.code === 'STALE_ACTIVATION';
            this.statuses[score.id] = stale
                ? 'La rutina cambió: el borrador no se enviará a otra gimnasta.'
                : 'Pendiente de sincronización. Se reintentará al recuperar conexión.';
        }
    }

    applyScoreMask(scoreId: string, event: Event): void {
        const input = event.target as HTMLInputElement;
        const digits = input.value.replace(/\D/g, '').slice(0, 4);

        if (digits && Number(digits) > SCORE_MAX * 100) {
            input.value = this.values[scoreId] ?? '';
            this.statuses[scoreId] = SCORE_RANGE_MESSAGE;
            return;
        }

        this.values[scoreId] = digits ? this.formatScoreDigits(digits) : '';
        input.value = this.values[scoreId];
        input.setSelectionRange(input.value.length, input.value.length);

        if (this.statuses[scoreId] === SCORE_RANGE_MESSAGE) {
            delete this.statuses[scoreId];
        }
    }

    startEditing(scoreId: string, event: FocusEvent): void {
        this.editingScoreId = scoreId;
        window.setTimeout(() => (event.target as HTMLInputElement).select(), 0);
    }

    stopEditing(scoreId: string): void {
        if (this.editingScoreId === scoreId) this.editingScoreId = null;
    }

    trackByContext(_index: number, context: JudgeContext): string {
        return context.assignment_id;
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
            this.values[score.id] = this.formatScoreValue(draft.value);
            await this.save(context);
        }
    }

    private key(scoreId: string): string { return `ritmica-judge-draft:${scoreId}`; }
    private persistDraft(scoreId: string, draft: LocalDraft): void { localStorage.setItem(this.key(scoreId), JSON.stringify(draft)); }
    private readDraft(scoreId: string): LocalDraft | null {
        try { return JSON.parse(localStorage.getItem(this.key(scoreId)) ?? 'null') as LocalDraft | null; } catch { return null; }
    }
    private removeDraft(scoreId: string): void { localStorage.removeItem(this.key(scoreId)); }

    private formatScoreValue(value: string): string {
        if (!String(value).trim()) return '';
        const digits = this.toScoreDigits(value);
        return digits ? this.formatScoreDigits(digits) : '';
    }

    private isCompleteScoreValue(value: string | undefined): boolean {
        return value !== undefined
            && /^\d{1,2}\.\d{2}$/.test(value)
            && Number(value) >= 0
            && Number(value) <= SCORE_MAX;
    }

    private toScoreDigits(value: string): string {
        const numericValue = Number(String(value).replace(',', '.'));
        if (!Number.isFinite(numericValue) || numericValue < 0 || numericValue > SCORE_MAX) {
            return '';
        }
        return String(Math.round(numericValue * 100));
    }

    private formatScoreDigits(digits: string): string {
        return (Number(digits) / 100).toFixed(2);
    }
}
