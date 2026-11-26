"""Ces fichiers sont des copies pour nota : pytest ne doit pas les collecter dans adam.

Ils importent nota_worker, absent d'adam. Chaque fichier se recopie a la meme
place dans nota-back (meme chemin, sans le prefixe nota-a-copier/).
"""

collect_ignore_glob = ["*"]
