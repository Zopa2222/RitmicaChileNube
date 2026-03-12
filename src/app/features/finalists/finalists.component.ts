import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { ApiService } from '../../core/services/api.service';

interface FinalistGymnast {
  rut: string;
  nombre: string;
  club: string;
  puntajeTotal: number;
  controles: { campeonato: string; puntajeTotal: number }[];
}

interface FinalistCategory {
  categoria: string;
  finalistas: FinalistGymnast[];
}

@Component({
  selector: 'app-finalists',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatSelectModule,
    MatFormFieldModule,
    MatProgressSpinnerModule,
    MatSnackBarModule
  ],
  templateUrl: './finalists.component.html',
  styleUrls: ['./finalists.component.scss']
})
export class FinalistsComponent {
  zonas = [
    { value: 'norte',  label: 'Zona Norte' },
    { value: 'centro', label: 'Zona Centro' },
    { value: 'sur',    label: 'Zona Sur' }
  ];

  readonly currentYear = new Date().getFullYear();
  years: number[] = Array.from({ length: 5 }, (_, i) => this.currentYear - i);

  selectedZona: string = '';
  selectedAnio: number = this.currentYear;
  loading = false;
  exporting = false;
  exportingExcel = false;
  categories: FinalistCategory[] = [];
  loaded = false;
  errorMsg = '';

  // Tracks expanded gymnast: 'categoryName__rutOrNombre'
  expandedKey: string | null = null;

  constructor(
    private apiService: ApiService,
    private router: Router,
    private snackBar: MatSnackBar
  ) {}

  loadFinalists(): void {
    if (!this.selectedZona) return;
    this.loading = true;
    this.loaded = false;
    this.errorMsg = '';
    this.categories = [];

    this.apiService.getFinalists(this.selectedZona, this.selectedAnio).subscribe({
      next: (res) => {
        this.categories = res.categorias || [];
        this.loaded = true;
        this.loading = false;
        if (this.categories.length === 0) {
          this.errorMsg = 'No se encontraron datos para esta zona. Verifique que los campeonatos estén cargados.';
        }
      },
      error: (err) => {
        this.loading = false;
        this.errorMsg = err.error?.error || 'Error al cargar finalistas.';
        this.snackBar.open(this.errorMsg, 'Cerrar', { duration: 4000 });
      }
    });
  }

  exportPdf(): void {
    if (!this.selectedZona) return;
    this.exporting = true;

    this.apiService.exportFinalistsPdf(this.selectedZona, this.selectedAnio).subscribe({
      next: (blob) => {
        const zonaLabel = this.zonas.find(z => z.value === this.selectedZona)?.label || this.selectedZona;
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `Finalistas_${zonaLabel}_${this.selectedAnio}.pdf`;
        link.click();
        window.URL.revokeObjectURL(url);
        this.exporting = false;
        this.snackBar.open('PDF descargado', 'OK', { duration: 2000 });
      },
      error: () => {
        this.exporting = false;
        this.snackBar.open('Error al exportar PDF', 'Cerrar', { duration: 3000 });
      }
    });
  }

  exportExcel(): void {
    if (!this.selectedZona) return;
    this.exportingExcel = true;

    this.apiService.exportFinalistsExcel(this.selectedZona, this.selectedAnio).subscribe({
      next: (blob) => {
        const zonaLabel = this.zonas.find(z => z.value === this.selectedZona)?.label || this.selectedZona;
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `Finalistas_${zonaLabel}_${this.selectedAnio}.xlsx`;
        link.click();
        window.URL.revokeObjectURL(url);
        this.exportingExcel = false;
        this.snackBar.open('Excel descargado', 'OK', { duration: 2000 });
      },
      error: () => {
        this.exportingExcel = false;
        this.snackBar.open('Error al exportar Excel', 'Cerrar', { duration: 3000 });
      }
    });
  }

  toggleExpand(catName: string, gymnast: FinalistGymnast): void {
    if (gymnast.controles?.length <= 1) return; // nothing to expand if only 1 control
    const key = `${catName}__${gymnast.rut || gymnast.nombre}`;
    this.expandedKey = this.expandedKey === key ? null : key;
  }

  isExpanded(catName: string, gymnast: FinalistGymnast): boolean {
    const key = `${catName}__${gymnast.rut || gymnast.nombre}`;
    return this.expandedKey === key;
  }

  hasMultipleControls(gymnast: FinalistGymnast): boolean {
    return (gymnast.controles?.length ?? 0) > 1;
  }

  getZonaLabel(): string {
    return this.zonas.find(z => z.value === this.selectedZona)?.label || '';
  }

  getTitle(): string {
    return `${this.getZonaLabel()} — ${this.selectedAnio}`;
  }

  goHome(): void {
    this.router.navigate(['/']);
  }
}
