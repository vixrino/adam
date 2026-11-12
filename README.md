    table = sa.table(  
        "test_execution",  
        sa.column("documents_traites", sa.Integer()),  
        sa.column("documents_compared", sa.Integer()),  
        schema=SCHEMA,  
    ) 
    op.execute(table.update().values(documents_traites=table.c.documents_compared)) 
