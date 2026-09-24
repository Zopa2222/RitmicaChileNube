import { Injectable } from '@angular/core';

/** Keeps selected files alive while navigating from creation to import review. */
@Injectable({ providedIn: 'root' })
export class InitialImportQueueService {
    championshipId: string | null = null;
    days: Array<{ date: string; file: File }> = [];
}
