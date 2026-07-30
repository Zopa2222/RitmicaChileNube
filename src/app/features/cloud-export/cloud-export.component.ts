import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { CloudExportApiService } from '../../core/services/cloud-export-api.service';

@Component({
    selector: 'app-cloud-export', standalone: true,
    imports: [MatButtonModule, MatIconModule, RouterLink],
    templateUrl: './cloud-export.component.html', styleUrls: ['./cloud-export.component.scss']
})
export class CloudExportComponent {
    readonly championshipId = this.route.snapshot.paramMap.get('championshipId') ?? '';
    message = '';
    downloading = false;
    constructor(private readonly route: ActivatedRoute, private readonly exportApi: CloudExportApiService) { }
    async download(format: 'excel' | 'pdf'): Promise<void> {
        this.downloading = true; this.message = '';
        try {
            const blob = await firstValueFrom(this.exportApi.download(this.championshipId, format));
            const url = URL.createObjectURL(blob); const link = document.createElement('a');
            link.href = url; link.download = `resultados.${format === 'excel' ? 'xlsx' : 'pdf'}`; link.click(); URL.revokeObjectURL(url);
        } catch { this.message = 'No fue posible generar la exportación.'; }
        finally { this.downloading = false; }
    }
}
