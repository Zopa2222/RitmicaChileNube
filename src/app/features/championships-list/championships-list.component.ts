import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { MatTooltipModule } from '@angular/material/tooltip';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import { ApiService } from '../../core/services/api.service';
import { ChampionshipService } from '../../core/services/championship.service';
import { Championship } from '../../core/models/championship.model';

interface ChampionshipItem {
  id: string;
  nombre: string;
  categorias: string[];
  jueces: Array<{ 
    nombre: string; 
    rol?: string; 
    banca?: 'A' | 'B'; 
    rol_am?: string | null; 
    rol_pm?: string | null; 
  }>;
  created_at: string;
}

@Component({
  selector: 'app-championships-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTooltipModule
  ],
  templateUrl: './championships-list.component.html',
  styleUrls: ['./championships-list.component.scss']
})
export class ChampionshipsListComponent implements OnInit {
  championships: ChampionshipItem[] = [];
  filteredChampionships: ChampionshipItem[] = [];
  searchTerm: string = '';
  loading: boolean = false;

  constructor(
    private apiService: ApiService,
    private championshipService: ChampionshipService,
    private router: Router,
    private snackBar: MatSnackBar
  ) { }

  ngOnInit(): void {
    this.loadChampionships();
  }

  loadChampionships(): void {
    this.loading = true;
    this.apiService.getChampionships().subscribe({
      next: (response) => {
        console.log('Championships loaded:', response); // DEBUG
        this.championships = response.campeonatos;
        this.filteredChampionships = this.championships;

        // DEBUG: Log first championship to verify judges
        if (this.championships.length > 0) {
          console.log('First championship jueces:', this.championships[0].jueces);
        }

        this.loading = false;
      },
      error: (err) => {
        console.error('Error loading championships:', err);
        this.snackBar.open('Error al cargar campeonatos', 'Cerrar', { duration: 3000 });
        this.loading = false;
      }
    });
  }

  filterChampionships(): void {
    const term = this.searchTerm.toLowerCase();
    this.filteredChampionships = this.championships.filter(c =>
      c.nombre.toLowerCase().includes(term)
    );
  }

  downloadExcel(championship: ChampionshipItem): void {
    this.apiService.exportChampionship(championship.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${championship.nombre}_resultados.xlsx`;
        link.click();
        window.URL.revokeObjectURL(url);
        this.snackBar.open('Descarga iniciada', 'OK', { duration: 2000 });
      },
      error: (err) => {
        console.error('Error downloading:', err);
        this.snackBar.open('Error al descargar', 'Cerrar', { duration: 3000 });
      }
    });
  }

  downloadPdf(championship: ChampionshipItem): void {
    this.apiService.exportChampionshipPdf(championship.id).subscribe({
      next: (blob) => {
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${championship.nombre}_resultados.pdf`;
        link.click();
        window.URL.revokeObjectURL(url);
        this.snackBar.open('Descarga de PDF iniciada', 'OK', { duration: 2000 });
      },
      error: (err) => {
        console.error('Error downloading PDF:', err);
        this.snackBar.open('Error al descargar PDF', 'Cerrar', { duration: 3000 });
      }
    });
  }

  editChampionship(championship: ChampionshipItem): void {
    // Map API jueces to BancaJudge[] per banca
    const bancaA: any[] = [];
    const bancaB: any[] = [];

    for (const j of championship.jueces) {
      const banca = (j as any).banca || 'A';
      const bancaJudge = {
        name: j.nombre,
        roleAM: (j as any).rol_am || (j as any).rol || null,
        rolePM: (j as any).rol_pm || (j as any).rol || null
      };

      if (banca === 'B') {
        bancaB.push(bancaJudge);
      } else {
        bancaA.push(bancaJudge);
      }
    }

    const categoriasBanca = (championship as any).categorias_banca || {};

    const champ: Championship = {
      id: championship.id,
      name: championship.nombre,
      bancaA: bancaA,
      bancaB: bancaB,
      categoriasBanca: categoriasBanca,
      categories: championship.categorias.map(catName => ({
        name: catName,
        gymnasts: []
      }))
    };

    this.championshipService.setChampionship(champ);
    this.router.navigate(['/scoring']);
  }

  goHome(): void {
    this.router.navigate(['/']);
  }

  getJudgesNames(jueces: any[]): string {
    if (!jueces || jueces.length === 0) return '';
    return jueces.map(j => j.nombre).join(', ');
  }

  getJudgeRoleDescription(juez: any): string {
    if (!juez) return '';
    if (juez.banca) {
      const am = juez.rol_am || '—';
      const pm = juez.rol_pm || '—';
      return `Banca ${juez.banca} (AM: ${am} | PM: ${pm})`;
    }
    return juez.rol || '';
  }

  formatDate(dateString: string): string {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('es-CL', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
  }
}
