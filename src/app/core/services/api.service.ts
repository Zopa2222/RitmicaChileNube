import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Championship } from '../models/championship.model';
import { Category } from '../models/category.model';

@Injectable({
    providedIn: 'root'
})
export class ApiService {
    private readonly API_URL = 'http://localhost:8080';

    constructor(private http: HttpClient) { }

    /**
     * Create a new championship
     * POST /campeonatos
     */
    createChampionship(name: string): Observable<any> {
        return this.http.post<any>(`${this.API_URL}/campeonatos`, { nombre: name });
    }

    /**
     * Add a judge to the championship
     * POST /campeonatos/{id}/jueces
     */
    addJudge(championshipId: string, judge: { nombre: string, rol: string }): Observable<any> {
        return this.http.post<any>(`${this.API_URL}/campeonatos/${championshipId}/jueces`, judge);
    }

    /**
     * Upload Excel file with orden de paso
     * POST /campeonatos/{id}/orden-paso
     */
    uploadExcel(championshipId: string, file: File): Observable<any> {
        const formData = new FormData();
        formData.append('file', file);
        return this.http.post<any>(`${this.API_URL}/campeonatos/${championshipId}/orden-paso`, formData);
    }

    /**
     * Get category by ID with all gymnasts
     * GET /campeonatos/{id}/categorias/{categoryName}
     */
    getCategory(championshipId: string, categoryName: string): Observable<any> {
        return this.http.get<any>(`${this.API_URL}/campeonatos/${championshipId}/categorias/${categoryName}`);
    }

    /**
     * Update category (save scores)
     * PUT /campeonatos/{id}/categorias/{categoryName}
     */
    updateCategory(championshipId: string, categoryName: string, gymnasts: any[]): Observable<any> {
        return this.http.put<any>(`${this.API_URL}/campeonatos/${championshipId}/categorias/${categoryName}`, {
            gimnastas: gymnasts
        });
    }

    /**
     * Get all championships
     * GET /campeonatos
     */
    getChampionships(): Observable<any> {
        return this.http.get<any>(`${this.API_URL}/campeonatos`);
    }

    /**
     * Get categories for a championship
     * GET /campeonatos/{id}/categorias
     */
    getCategories(championshipId: string): Observable<any> {
        return this.http.get<any>(`${this.API_URL}/campeonatos/${championshipId}/categorias`);
    }

    /**
     * Export championship to Excel
     * GET /campeonatos/{id}/export
     */
    exportChampionship(championshipId: string): Observable<Blob> {
        return this.http.get(`${this.API_URL}/campeonatos/${championshipId}/export`, {
            responseType: 'blob'
        });
    }
}
