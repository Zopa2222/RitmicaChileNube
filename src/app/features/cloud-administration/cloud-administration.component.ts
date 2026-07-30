import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { firstValueFrom } from 'rxjs';

import { AuditLogEntry, CloudJudge } from '../../core/models/cloud.model';
import { CloudAdministrationApiService } from '../../core/services/cloud-administration-api.service';

@Component({
    selector: 'app-cloud-administration',
    standalone: true,
    imports: [CommonModule, FormsModule, MatButtonModule, MatIconModule],
    templateUrl: './cloud-administration.component.html',
    styleUrls: ['./cloud-administration.component.scss']
})
export class CloudAdministrationComponent implements OnInit, OnDestroy {
    judges: CloudJudge[] = [];
    logs: AuditLogEntry[] = [];
    query = '';
    message = '';
    newJudge = { first_name: '', last_name: '', rut: '' };
    newPassword = '';
    credentials: { username: string; password: string } | null = null;
    private logTimer: number | null = null;

    constructor(private readonly administrationApi: CloudAdministrationApiService) { }

    ngOnInit(): void {
        void this.load();
        this.logTimer = window.setInterval(() => void this.loadLogs(), 5000);
    }

    ngOnDestroy(): void { if (this.logTimer !== null) window.clearInterval(this.logTimer); }

    async load(): Promise<void> { await Promise.all([this.loadJudges(), this.loadLogs()]); }
    async loadJudges(): Promise<void> {
        try { this.judges = await firstValueFrom(this.administrationApi.judges(this.query)); }
        catch { this.message = 'No fue posible cargar los jueces.'; }
    }
    async loadLogs(): Promise<void> {
        try { this.logs = await firstValueFrom(this.administrationApi.auditLogs()); }
        catch { /* The judge tools remain usable if audit polling is temporarily unavailable. */ }
    }

    async createJudge(): Promise<void> {
        try {
            const response = await firstValueFrom(this.administrationApi.createJudge(this.newJudge));
            this.credentials = response.credentials;
            this.newJudge = { first_name: '', last_name: '', rut: '' };
            await this.loadJudges();
        } catch { this.message = 'Revisa nombre, apellido y RUT antes de crear la cuenta.'; }
    }

    async regenerate(judge: CloudJudge): Promise<void> {
        if (!window.confirm(`Regenerar las credenciales de ${judge.first_name}?`)) return;
        try {
            const response = await firstValueFrom(this.administrationApi.regenerateCredentials(judge.id));
            this.credentials = response.credentials;
            await this.loadJudges();
        } catch { this.message = 'No fue posible regenerar las credenciales.'; }
    }

    async disable(judge: CloudJudge): Promise<void> {
        if (!window.confirm(`Deshabilitar a ${judge.first_name} ${judge.last_name}?`)) return;
        try { await firstValueFrom(this.administrationApi.disableJudge(judge.id)); await this.loadJudges(); }
        catch { this.message = 'No fue posible deshabilitar al juez.'; }
    }

    async recoverAdministrator(): Promise<void> {
        if (!this.newPassword) return;
        if (!window.confirm('Confirmo que verifiqué la identidad del administrador global.')) return;
        try {
            await firstValueFrom(this.administrationApi.recoverGlobalAdministrator(this.newPassword));
            this.newPassword = '';
            this.message = 'Acceso del administrador global recuperado.';
            await this.loadLogs();
        } catch { this.message = 'La contraseña debe tener al menos 12 caracteres.'; }
    }
}
