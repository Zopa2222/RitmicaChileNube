import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import Swal from 'sweetalert2';
import { JudgeLinkDeliveryComponent } from '../../shared/judge-link-delivery.component';

import { AuditLogEntry, CloudJudge } from '../../core/models/cloud.model';
import {
    CredentialDeliveryEntry,
    CredentialDeliveryService
} from '../../core/services/credential-delivery.service';
import { CloudAdministrationApiService } from '../../core/services/cloud-administration-api.service';
import {
    formatRutInput,
    normalizeRut,
    rutValidationCode,
    rutValidator
} from '../../core/utils/rut.utils';

@Component({
    selector: 'app-cloud-administration',
    standalone: true,
    imports: [JudgeLinkDeliveryComponent, CommonModule, FormsModule, ReactiveFormsModule, MatButtonModule, MatIconModule],
    templateUrl: './cloud-administration.component.html',
    styleUrls: ['./cloud-administration.component.scss']
})
export class CloudAdministrationComponent implements OnInit, OnDestroy {
    judges: CloudJudge[] = [];
    logs: AuditLogEntry[] = [];
    query = '';
    message = '';
    newPassword = '';
    selectedJudgeIds = new Set<string>();
    visibleCredentialIds = new Set<string>();
    regenerating = false;
    readonly credentialEntries$ = this.credentialDelivery.entries$;
    readonly newJudgeForm = this.formBuilder.nonNullable.group({
        first_name: ['', [Validators.required, Validators.maxLength(100)]],
        last_name: ['', [Validators.required, Validators.maxLength(100)]],
        rut: ['', [Validators.required, rutValidator]]
    });
    private logTimer: number | null = null;
    readonly section: 'configuration' | 'judges';

    constructor(
        private readonly route: ActivatedRoute,
        private readonly formBuilder: FormBuilder,
        private readonly administrationApi: CloudAdministrationApiService,
        private readonly credentialDelivery: CredentialDeliveryService
    ) {
        this.section = this.route.snapshot.data['section'] === 'judges'
            ? 'judges'
            : 'configuration';
    }

    get isConfiguration(): boolean {
        return this.section === 'configuration';
    }

    ngOnInit(): void {
        if (this.isConfiguration) {
            void this.loadLogs();
            this.logTimer = window.setInterval(() => void this.loadLogs(), 5000);
            return;
        }
        void this.loadJudges();
        this.logTimer = window.setInterval(() => void this.loadJudges(), 10000);
    }

    ngOnDestroy(): void {
        if (this.logTimer !== null) window.clearInterval(this.logTimer);
    }

    get selectedCount(): number { return this.selectedJudgeIds.size; }

    get selectableJudges(): CloudJudge[] {
        return this.judges.filter((judge) => judge.status !== 'DISABLED');
    }

    get allVisibleSelected(): boolean {
        return this.selectableJudges.length > 0
            && this.selectableJudges.every((judge) =>
                this.selectedJudgeIds.has(judge.id)
            );
    }

    async loadJudges(): Promise<void> {
        try {
            this.judges = await firstValueFrom(this.administrationApi.judges(this.query));
            const visibleIds = new Set(this.selectableJudges.map((judge) => judge.id));
            this.selectedJudgeIds = new Set([...this.selectedJudgeIds].filter((id) => visibleIds.has(id)));
        } catch { this.message = 'No fue posible cargar los jueces.'; }
    }

    async loadLogs(): Promise<void> {
        try { this.logs = await firstValueFrom(this.administrationApi.auditLogs()); }
        catch { /* The judge tools remain usable if audit polling is temporarily unavailable. */ }
    }

    formatRutField(event?: Event): void {
        const control = this.newJudgeForm.controls.rut;
        const input = event?.target as HTMLInputElement | undefined;
        const formatted = formatRutInput(input?.value ?? control.value);
        if (input) input.value = formatted;
        control.setValue(formatted, { emitEvent: false });
    }

    async createJudge(): Promise<void> {
        if (this.newJudgeForm.invalid) {
            this.newJudgeForm.markAllAsTouched();
            return;
        }
        try {
            const value = this.newJudgeForm.getRawValue();
            const response = await firstValueFrom(this.administrationApi.createJudge({
                first_name: value.first_name.trim(),
                last_name: value.last_name.trim(),
                rut: normalizeRut(value.rut)
            }));
            this.credentialDelivery.add(response.judge, response.credentials);
            this.newJudgeForm.reset();
            await this.loadJudges();
        } catch { this.message = 'Revisa nombre, apellido y RUT antes de crear la cuenta.'; }
    }

    async regenerate(judge: CloudJudge): Promise<void> {
        const confirmation = await Swal.fire({
            title: '¿Generar un enlace de acceso?',
            text: `El enlace anterior de ${judge.first_name} y sus sesiones dejarán de funcionar.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Generar enlace',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmation.isConfirmed) return;
        try {
            const response = await firstValueFrom(this.administrationApi.regenerateCredentials(judge.id));
            this.credentialDelivery.add(response.judge, response.credentials);
            await this.loadJudges();
        } catch { this.message = 'No fue posible generar el enlace.'; }
    }

    async regenerateSelected(): Promise<void> {
        const judgeIds = [...this.selectedJudgeIds];
        if (!judgeIds.length || this.regenerating) return;
        const confirmation = await Swal.fire({
            title: '¿Generar enlaces para los jueces seleccionados?',
            text: `Se generarán ${judgeIds.length} enlaces. Los enlaces anteriores y sus sesiones dejarán de funcionar.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Generar enlace',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmation.isConfirmed) return;
        this.regenerating = true;
        try {
            const items = await firstValueFrom(this.administrationApi.regenerateCredentialsBatch(judgeIds));
            items.forEach((item) => this.credentialDelivery.add(item.judge, item.credentials));
            this.selectedJudgeIds = new Set();
            await this.loadJudges();
        } catch { this.message = 'No fue posible generar los enlaces seleccionados.'; }
        finally { this.regenerating = false; }
    }

    toggleJudge(judgeId: string, checked: boolean): void {
        if (checked) this.selectedJudgeIds.add(judgeId);
        else this.selectedJudgeIds.delete(judgeId);
        this.selectedJudgeIds = new Set(this.selectedJudgeIds);
    }

    toggleAll(checked: boolean): void {
        this.selectedJudgeIds = checked
            ? new Set(this.selectableJudges.map((judge) => judge.id))
            : new Set();
    }

    isCredentialVisible(entry: CredentialDeliveryEntry): boolean {
        return this.visibleCredentialIds.has(entry.judgeId);
    }

    toggleCredentialVisibility(entry: CredentialDeliveryEntry): void {
        if (this.visibleCredentialIds.has(entry.judgeId)) this.visibleCredentialIds.delete(entry.judgeId);
        else this.visibleCredentialIds.add(entry.judgeId);
        this.visibleCredentialIds = new Set(this.visibleCredentialIds);
    }

    async clearCredentials(): Promise<void> {
        if (this.credentialDelivery.entries.length) {
            const confirmation = await Swal.fire({
                title: '¿Vaciar bandeja de enlaces?',
                text: 'Los enlaces mostrados se eliminarán de esta bandeja y no se podrán recuperar.',
                icon: 'warning',
                showCancelButton: true,
                confirmButtonText: 'Vaciar bandeja',
                cancelButtonText: 'Cancelar',
                confirmButtonColor: '#dc2626'
            });
            if (!confirmation.isConfirmed) return;
        }
        this.credentialDelivery.clear();
        this.visibleCredentialIds = new Set();
    }

    async editJudge(judge: CloudJudge): Promise<void> {
        const result = await Swal.fire({
            title: 'Editar juez',
            html: `
                <input id="judge-first-name" class="swal2-input" placeholder="Nombre" value="${this.escapeHtml(judge.first_name)}">
                <input id="judge-last-name" class="swal2-input" placeholder="Apellido" value="${this.escapeHtml(judge.last_name)}">
                <input id="judge-rut" class="swal2-input" placeholder="RUT" value="${formatRutInput(judge.rut)}">
            `,
            focusConfirm: false,
            showCancelButton: true,
            confirmButtonText: 'Guardar cambios',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#4f46e5',
            didOpen: () => {
                const rutInput = Swal.getPopup()
                    ?.querySelector('#judge-rut') as HTMLInputElement | null;
                rutInput?.addEventListener('input', () => {
                    rutInput.value = formatRutInput(rutInput.value);
                });
            },
            preConfirm: () => {
                const popup = Swal.getPopup();
                const firstName = (popup?.querySelector('#judge-first-name') as HTMLInputElement)
                    ?.value.trim();
                const lastName = (popup?.querySelector('#judge-last-name') as HTMLInputElement)
                    ?.value.trim();
                const rut = formatRutInput(
                    (popup?.querySelector('#judge-rut') as HTMLInputElement)?.value
                );
                if (!firstName || !lastName) {
                    Swal.showValidationMessage('Ingresa nombre y apellido');
                    return;
                }
                if (rutValidationCode(rut) !== null) {
                    Swal.showValidationMessage('Ingresa un RUT válido');
                    return;
                }
                return { firstName, lastName, rut };
            }
        });
        if (!result.isConfirmed || !result.value) return;
        try {
            await firstValueFrom(this.administrationApi.updateJudge(judge.id, {
                first_name: result.value.firstName,
                last_name: result.value.lastName,
                rut: normalizeRut(result.value.rut)
            }));
            this.message = 'Datos del juez actualizados.';
            await this.loadJudges();
        } catch {
            this.message = 'No fue posible actualizar los datos del juez.';
        }
    }

    async deleteJudge(judge: CloudJudge): Promise<void> {
        const confirmation = await Swal.fire({
            title: '¿Eliminar juez?',
            html: `Eliminarás permanentemente a <strong>${this.escapeHtml(judge.first_name)} ${this.escapeHtml(judge.last_name)}</strong> y sus credenciales. Esta acción no se puede deshacer.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Eliminar juez',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#dc2626'
        });
        if (!confirmation.isConfirmed) return;
        try {
            await firstValueFrom(this.administrationApi.deleteJudge(judge.id));
            this.selectedJudgeIds.delete(judge.id);
            this.selectedJudgeIds = new Set(this.selectedJudgeIds);
            this.message = 'Juez eliminado permanentemente.';
            await this.loadJudges();
        } catch { this.message = 'No fue posible eliminar al juez. Si tiene asignaciones, usa Desactivar para conservar su historial.'; }
    }

    async deactivateJudge(judge: CloudJudge): Promise<void> {
        const confirmation = await Swal.fire({
            title: '¿Desactivar juez?',
            text: `${judge.first_name} ${judge.last_name} no podrá iniciar sesión, pero sus asignaciones e historial se conservarán.`,
            icon: 'warning',
            showCancelButton: true,
            confirmButtonText: 'Desactivar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmation.isConfirmed) return;
        try {
            await firstValueFrom(this.administrationApi.deactivateJudge(judge.id));
            this.selectedJudgeIds.delete(judge.id);
            this.selectedJudgeIds = new Set(this.selectedJudgeIds);
            await this.loadJudges();
        } catch { this.message = 'No fue posible desactivar al juez.'; }
    }

    async activateJudge(judge: CloudJudge): Promise<void> {
        const confirmation = await Swal.fire({
            title: '¿Activar juez?',
            text: `${judge.first_name} ${judge.last_name} podrá volver a iniciar sesión.`,
            icon: 'question',
            showCancelButton: true,
            confirmButtonText: 'Activar',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#4f46e5'
        });
        if (!confirmation.isConfirmed) return;
        try {
            await firstValueFrom(this.administrationApi.activateJudge(judge.id));
            await this.loadJudges();
        } catch { this.message = 'No fue posible activar al juez.'; }
    }

    async recoverAdministrator(): Promise<void> {
        if (!this.newPassword) return;
        const confirmation = await Swal.fire({
            title: 'Recuperar administrador global',
            text: 'Confirma que verificaste la identidad del administrador global.',
            icon: 'warning',
            input: 'checkbox',
            inputPlaceholder: 'Identidad verificada',
            inputValidator: (checked) => checked
                ? undefined
                : 'Debes confirmar la verificación de identidad',
            showCancelButton: true,
            confirmButtonText: 'Recuperar acceso',
            cancelButtonText: 'Cancelar',
            confirmButtonColor: '#d97706'
        });
        if (!confirmation.isConfirmed) return;
        try {
            await firstValueFrom(this.administrationApi.recoverGlobalAdministrator(this.newPassword));
            this.newPassword = '';
            this.message = 'Acceso del administrador global recuperado.';
            await this.loadLogs();
        } catch { this.message = 'La contraseña debe tener al menos 12 caracteres.'; }
    }

    private escapeHtml(value: string): string {
        return value.replace(/[&<>'"]/g, (character) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            "'": '&#39;',
            '"': '&quot;'
        })[character] ?? character);
    }
}
