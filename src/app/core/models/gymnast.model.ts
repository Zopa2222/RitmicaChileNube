// Gymnast interface
export interface Gymnast {
    id?: string;
    name: string;
    club: string;
    scores: { [key: string]: number }; // DA, DB, E1, E2, A1, etc.
    desc: number; // Descuento
    totalScore: number;
    order: number; // Position in the list
}

// Create empty gymnast
export function createEmptyGymnast(order: number): Gymnast {
    return {
        name: '',
        club: '',
        scores: {},
        desc: 0,
        totalScore: 0,
        order
    };
}
