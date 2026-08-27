import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

import { AuthStateService } from '../auth/auth-state.service';
import { CloudJudge, InitialCredentials } from '../models/cloud.model';
import { formatRut } from '../utils/rut.utils';

export interface CredentialDeliveryEntry {
    judgeId: string;
    firstName: string;
    lastName: string;
    rut: string;
    username: string;
    password: string;
}

@Injectable({ providedIn: 'root' })
export class CredentialDeliveryService {
    private readonly entriesSubject =
        new BehaviorSubject<CredentialDeliveryEntry[]>([]);

    readonly entries$ = this.entriesSubject.asObservable();

    constructor(authState: AuthStateService) {
        authState.user$.subscribe((user) => {
            if (!user) this.clear();
        });
    }

    get entries(): CredentialDeliveryEntry[] {
        return this.entriesSubject.value;
    }

    add(judge: CloudJudge, credentials: InitialCredentials): void {
        const entry: CredentialDeliveryEntry = {
            judgeId: judge.id,
            firstName: judge.first_name,
            lastName: judge.last_name,
            rut: formatRut(judge.rut),
            username: credentials.username,
            password: credentials.password
        };
        const entries = this.entries.filter((item) => item.judgeId !== judge.id);
        this.entriesSubject.next([...entries, entry]);
    }

    clear(): void {
        this.entriesSubject.next([]);
    }
}
