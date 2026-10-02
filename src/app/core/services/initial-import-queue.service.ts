import { Injectable } from '@angular/core';

export interface InitialImportDay {
    date: string;
    file: File | null;
    fileName: string;
    previewId?: string;
}

/** Keeps selected files alive while navigating from creation to import review. */
@Injectable({ providedIn: 'root' })
export class InitialImportQueueService {
    championshipId: string | null = null;
    days: InitialImportDay[] = [];
}
