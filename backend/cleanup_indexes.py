"""
Script to clean up MongoDB databases:
1. Drop existing unique indexes on 'nombre' field
2. Recreate as non-unique indexes
3. Remove any documents with nombre='NOMBRE' (header rows)
"""

from pymongo import MongoClient

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')

# Get all database names
all_dbs = client.list_database_names()

# Filter championship databases
championship_dbs = [db for db in all_dbs if db.startswith('campeonato_')]

print(f"Found {len(championship_dbs)} championship databases")

for db_name in championship_dbs:
    print(f"\nProcessing database: {db_name}")
    db = client[db_name]
    
    # Get all collections except metadata and jueces
    collections = db.list_collection_names()
    category_collections = [col for col in collections if col not in ['metadata', 'jueces']]
    
    for collection_name in category_collections:
        print(f"  Processing collection: {collection_name}")
        collection = db[collection_name]
        
        # 1. Drop the unique index on 'nombre' if it exists
        indexes = collection.index_information()
        if 'nombre_1' in indexes:
            try:
                collection.drop_index('nombre_1')
                print(f"    ✓ Dropped unique index 'nombre_1'")
            except Exception as e:
                print(f"    ✗ Error dropping index: {e}")
        
        # 2. Remove documents with nombre='NOMBRE' (header rows)
        result = collection.delete_many({'nombre': {'$in': ['NOMBRE', 'NAME']}})
        if result.deleted_count > 0:
            print(f"    ✓ Removed {result.deleted_count} header row document(s)")
        
        # 3. Create non-unique index
        try:
            collection.create_index('nombre')
            print(f"    ✓ Created non-unique index on 'nombre'")
        except Exception as e:
            print(f"    ✗ Error creating index: {e}")

print("\n✓ Cleanup complete!")
client.close()
