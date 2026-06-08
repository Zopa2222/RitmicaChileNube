import { Injectable } from '@angular/core';
import * as XLSX from 'xlsx';
import { Category } from '../models/category.model';
import { Gymnast } from '../models/gymnast.model';

@Injectable({
    providedIn: 'root'
})
export class ExcelService {

    /**
     * Parse Excel file and extract categories with gymnasts
     */
    parseExcelFile(file: File): Promise<Category[]> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();

            reader.onload = (e: any) => {
                try {
                    const data = new Uint8Array(e.target.result);
                    const workbook = XLSX.read(data, { type: 'array' });

                    const categories = this.extractCategoriesFromWorkbook(workbook);
                    resolve(categories);
                } catch (error) {
                    reject(error);
                }
            };

            reader.onerror = () => reject(new Error('Error reading file'));
            reader.readAsArrayBuffer(file);
        });
    }

    /**
     * Extract categories and gymnasts from workbook
     */
    private extractCategoriesFromWorkbook(workbook: XLSX.WorkBook): Category[] {
        const categoriesMap = new Map<string, Gymnast[]>();

        // Iterate through all sheets
        workbook.SheetNames.forEach(sheetName => {
            const worksheet = workbook.Sheets[sheetName];
            const jsonData: any[][] = XLSX.utils.sheet_to_json(worksheet, { header: 1 });

            // Find header row (contains "NOMBRE")
            let headerRowIndex = -1;
            for (let i = 0; i < Math.min(20, jsonData.length); i++) {
                const row = jsonData[i];
                if (row && row.some((cell: any) =>
                    cell && cell.toString().toUpperCase().includes('NOMBRE')
                )) {
                    headerRowIndex = i;
                    break;
                }
            }

            if (headerRowIndex === -1) return;

            // Extract gymnasts from BANCA A and BANCA B
            for (let i = headerRowIndex + 1; i < jsonData.length; i++) {
                const row = jsonData[i];
                if (!row || row.length === 0) continue;

                // BANCA A (columns 0-3: N, NOMBRE, CLUB, CATEGORIA)
                if (row[1] && row[3]) {
                    this.addGymnastToCategory(categoriesMap, {
                        name: row[1].toString().trim(),
                        club: row[2] ? row[2].toString().trim() : '',
                        category: row[3].toString().trim()
                    });
                }

                // BANCA B (columns 4-7: N, NOMBRE, CLUB, CATEGORIA)
                if (row[5] && row[7]) {
                    this.addGymnastToCategory(categoriesMap, {
                        name: row[5].toString().trim(),
                        club: row[6] ? row[6].toString().trim() : '',
                        category: row[7].toString().trim()
                    });
                }
            }
        });

        // Convert map to array of categories
        const categories: Category[] = [];
        categoriesMap.forEach((gymnasts, categoryName) => {
            categories.push({
                name: categoryName,
                gymnasts: gymnasts.map((g, index) => ({
                    ...g,
                    order: index
                }))
            });
        });

        return categories.sort((a, b) => a.name.localeCompare(b.name));
    }

    /**
     * Add gymnast to category map
     */
    private addGymnastToCategory(
        categoriesMap: Map<string, Gymnast[]>,
        data: { name: string; club: string; category: string }
    ): void {
        if (!categoriesMap.has(data.category)) {
            categoriesMap.set(data.category, []);
        }

        const gymnasts = categoriesMap.get(data.category)!;
        gymnasts.push({
            name: data.name,
            club: data.club,
            scores: {},
            desc: 0,
            totalScore: 0,
            order: gymnasts.length
        });
    }

    /**
     * Export categories to Excel file
     */
    exportToExcel(categories: Category[], championshipName: string): void {
        const workbook = XLSX.utils.book_new();

        categories.forEach(category => {
            // Sort gymnasts by total score (highest first), then by E score, then by A score for tiebreaker
            const sortedGymnasts = [...category.gymnasts].sort((a, b) => {
                // Primary: sort by total score (descending)
                if (b.totalScore !== a.totalScore) {
                    return b.totalScore - a.totalScore;
                }

                // First tiebreaker: sort by E score (descending)
                const eScoreA = this.calculateEScore(a);
                const eScoreB = this.calculateEScore(b);
                if (eScoreB !== eScoreA) {
                    return eScoreB - eScoreA;
                }

                // Second tiebreaker: sort by A score (descending)
                const aScoreA = this.calculateAScore(a);
                const aScoreB = this.calculateAScore(b);
                return aScoreB - aScoreA;
            });

            // Prepare data for sheet
            const sheetData: any[][] = [];

            // Header row
            const headers = ['Posición', 'Nombre', 'Club'];
            const scoreColumns = Object.keys(sortedGymnasts[0]?.scores || {}).sort();
            headers.push(...scoreColumns, 'Desc', 'Total');
            sheetData.push(headers);

            // Data rows
            sortedGymnasts.forEach((gymnast, index) => {
                const row: any[] = [
                    index + 1,
                    gymnast.name,
                    gymnast.club
                ];

                scoreColumns.forEach(col => {
                    row.push(gymnast.scores[col] || 0);
                });

                row.push(gymnast.desc, gymnast.totalScore.toFixed(2));
                sheetData.push(row);
            });

            // Create worksheet
            const worksheet = XLSX.utils.aoa_to_sheet(sheetData);

            // Add worksheet to workbook (limit sheet name to 31 chars)
            const sheetName = category.name.substring(0, 31);
            XLSX.utils.book_append_sheet(workbook, worksheet, sheetName);
        });

        // Download file
        const fileName = `${championshipName}_resultados.xlsx`;
        XLSX.writeFile(workbook, fileName);
    }

    /**
     * Calculate E score for a gymnast (for tiebreaker purposes)
     */
    private calculateEScore(gymnast: Gymnast): number {
        // Get E judge scores and calculate E score (10 - deduction)
        const eKeys = Object.keys(gymnast.scores).filter(key => key.startsWith('E'));
        if (eKeys.length === 0) return 0;

        const eScores = eKeys.map(key => gymnast.scores[key]);
        const deduction = this.calculateDeduction(eScores);
        return 10 - deduction;
    }

    /**
     * Calculate A score for a gymnast (for second tiebreaker purposes)
     */
    private calculateAScore(gymnast: Gymnast): number {
        // Get A judge scores and calculate A score (10 - deduction)
        const aKeys = Object.keys(gymnast.scores).filter(key => key.startsWith('A'));
        if (aKeys.length === 0) return 0;

        const aScores = aKeys.map(key => gymnast.scores[key]);
        const deduction = this.calculateDeduction(aScores);
        return 10 - deduction;
    }

    /**
     * Calculate deduction from judge scores
     * Rules:
     * - 1 judge: use that score
     * - 2-3 judges: average all scores
     * - 4+ judges: average excluding min and max
     */
    private calculateDeduction(scores: number[]): number {
        if (scores.length === 0) return 0;
        if (scores.length === 1) return scores[0];
        if (scores.length <= 3) {
            return scores.reduce((sum, s) => sum + s, 0) / scores.length;
        }
        // 4+ judges: exclude min and max
        const sorted = [...scores].sort((a, b) => a - b);
        const middle = sorted.slice(1, -1);
        return middle.reduce((sum, s) => sum + s, 0) / middle.length;
    }
}
