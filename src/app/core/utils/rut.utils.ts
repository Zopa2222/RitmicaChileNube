import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export type RutValidationCode = 'format' | 'checkDigit';

export function normalizeRut(value: unknown): string {
    return String(value ?? '')
        .trim()
        .toLocaleUpperCase('es-CL')
        .replace(/[^0-9K]/g, '');
}

export function rutValidationCode(value: unknown): RutValidationCode | null {
    const rut = normalizeRut(value);
    if (!/^\d{6,8}[0-9K]$/.test(rut)) {
        return 'format';
    }

    let factor = 2;
    let total = 0;
    for (const digit of rut.slice(0, -1).split('').reverse()) {
        total += Number(digit) * factor;
        factor = factor === 7 ? 2 : factor + 1;
    }
    const remainder = 11 - (total % 11);
    const expected = remainder === 11 ? '0' : remainder === 10 ? 'K' : String(remainder);
    return rut.at(-1) === expected ? null : 'checkDigit';
}

export function formatRut(value: unknown): string {
    const rut = normalizeRut(value);
    if (!rut) return '';
    const body = rut.slice(0, -1);
    const checkDigit = rut.slice(-1);
    return `${formatRutBody(body)}-${checkDigit}`;
}

/**
 * Formats a RUT while it is being typed. A check digit is recognized after a
 * hyphen, or after an eight-digit body, so seven-digit RUTs remain easy to
 * enter as `1.234.567-8`.
 */
export function formatRutInput(value: unknown): string {
    const raw = String(value ?? '').toLocaleUpperCase('es-CL');
    const dashIndex = raw.indexOf('-');

    if (dashIndex >= 0) {
        const body = raw.slice(0, dashIndex).replace(/\D/g, '').slice(0, 8);
        const checkDigit = raw.slice(dashIndex + 1)
            .replace(/[^0-9K]/g, '')
            .slice(0, 1);
        return `${formatRutBody(body)}-${checkDigit}`;
    }

    let body = '';
    let checkDigit = '';
    for (const character of raw) {
        if (/\d/.test(character) && body.length < 8) {
            body += character;
        } else if (
            body.length === 8
            && !checkDigit
            && /[0-9K]/.test(character)
        ) {
            checkDigit = character;
        }
    }
    return checkDigit
        ? `${formatRutBody(body)}-${checkDigit}`
        : formatRutBody(body);
}

function formatRutBody(body: string): string {
    return body.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
}

export const rutValidator: ValidatorFn = (
    control: AbstractControl
): ValidationErrors | null => {
    const value = String(control.value ?? '').trim();
    if (!value) return null;
    const code = rutValidationCode(value);
    return code ? { rut: code } : null;
};
