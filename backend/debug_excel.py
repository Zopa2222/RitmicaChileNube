import sys
import os

# Add app directory to path so we can import services
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app.services.excel_service import parse_excel_file

def test_parser():
    file_path = '../CENTRO.xlsx'
    
    if not os.path.exists(file_path):
        print(f"Error: No encuentro el archivo {file_path}")
        return

    print(f"Abriendo {file_path}...")
    
    print(f"Abriendo {file_path}...")
    
    try:
        with open(file_path, 'rb') as f:
            categories = parse_excel_file(f)
            
        print(f"\nResultados del análisis:")
        print(f"Categorías encontradas: {len(categories)}")
        
        for name, gymnasts in categories.items():
            print(f"- {name}: {len(gymnasts)} gimnastas")
            if len(gymnasts) > 0:
                print(f"  Ejemplo: {gymnasts[0]}")
                
    except Exception as e:
        print(f"\nExcepción durante el análisis:")
        print(e)
        import traceback
        traceback.print_exc()
        print(f"\nExcepción durante el análisis:")
        print(e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_parser()
