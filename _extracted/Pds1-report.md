I'll process all Pds1 screenshots: first checking what's already converted, then transcribing each page into a structured report.

[REDACTED]
Only 3 Pds1 pages exist — converting the full 51-page PDF next.

[REDACTED]
[REDACTED]
Conversion finished. Reading and transcribing all 51 pages in batches.

[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
[REDACTED]
All 51 pages are transcribed. Compiling the structured report.

[REDACTED]
# Pds1 Screenshot Transcription Report (51 pages)

**Source:** lots PDF transcrits *(fichiers supprimés — anonymisation)*  
**Pages converted:** 4–51 from `Pds1 .pdf` (51 pages total)

---

## Unique Files Found

| # | File Path | Screenshots | Line Ranges |
|---|-----------|-------------|-------------|
| 1 | `scripts/form_demo_v0.3.json` | Pds1-01 → Pds1-31 | 466–1384 |
| 2 | `scripts/download_swagger.ps1` | Pds1-32 | 1–9 |
| 3 | `scripts/run-checks.ps1` | Pds1-33 → Pds1-34 | 1–51 |
| 4 | `scripts/run_dev.py` | Pds1-35 | 1–20 |
| 5 | `scripts/seed.py` | Pds1-36 → Pds1-48 | 1–457 |
| 6 | `scripts/test_connection.py` | Pds1-49 → Pds1-51 | 1–87 |

---

## Global Gaps

| File | Missing Lines | Notes |
|------|---------------|-------|
| `scripts/form_demo_v0.3.json` | **1–465** | Entire file header / pages 1–3 not in Pds1 |
| `scripts/form_demo_v0.3.json` | **922–934** | Between Pds1-18 (ends ~929) and Pds1-19 (starts 935) |
| `scripts/form_demo_v0.3.json` | **1175–1177** | Pds1-25 ends at 1186 with `group_id: "dette_2"` but Pds1-26 starts at 1178 with `id: "endettement.logement"` — intermediate `group_id` line unclear |
| `scripts/form_demo_v0.3.json` | **1345–1347** | Pds1-30 ends mid-`dette_2` block; Pds1-31 jumps to `nom_creancier` — boolean debt-type fields for `dette_2` missing |
| All other files | None | Appear complete within Pds1 |

**OCR conflicts on overlapping lines** (resolve manually):
- MSA demandeur: `"12345678901"` (p03) vs `"12345678901"` (p04)
- MSA co-demandeur: `"98765432109"` (p04) vs `"98765432109"` (p05)
- `group_id`: `"Categorie"` / `"Boolean"` (p07) vs lowercase elsewhere
- `polygon`: `[0,0,0,0,0,0,0,0]` vs `[[0,0,0,0,0,0,0,0]]` (p29, p31)
- `seed.py` imports: `adam.core.*` (p36) vs `adam_core.*` (p37) — likely `adam_core`

---

## File 1: `scripts/form_demo_v0.3.json`

### Coverage Map (by screenshot)

| Page | Lines |
|------|-------|
| Pds1-01 | 466–504 |
| Pds1-02 | 495–533 |
| Pds1-03 | 523–561 |
| Pds1-04 | 544–582 |
| Pds1-05 | 567–605 |
| Pds1-06 | 597–635 |
| Pds1-07 | 623–661 |
| Pds1-08 | 646–684 |
| Pds1-09 | 670–708 |
| Pds1-10 | 694–732 |
| Pds1-11 | 727–764 |
| Pds1-12 | 744–782 |
| Pds1-13 | 762–799 |
| Pds1-14 | 783–821 |
| Pds1-15 | 805–843 |
| Pds1-16 | 824–862 |
| Pds1-17 | 861–899 |
| Pds1-18 | 891–929 |
| Pds1-19 | 935–973 |
| Pds1-20 | 972–1010 |
| Pds1-21 | 1012–1050 |
| Pds1-22 | 1046–1084 |
| Pds1-23 | 1082–1119 |
| Pds1-24 | 1113–1150 |
| Pds1-25 | 1148–1186 |
| Pds1-26 | 1178–1216 |
| Pds1-27 | 1208–1246 |
| Pds1-28 | 1235–1273 |
| Pds1-29 | 1272–1310 |
| Pds1-30 | 1311–1348 |
| Pds1-31 | 1346–1384 |

### Transcribed Content

```json
// GAP: lines 1–465 not captured

466:                "id": "situation_logement_demandeur2",
467:                "label": "Situation logement demandeur 2",
468:                "kv_pairs": [
469:                    {
470:                        "id": "situation_logement_demandeur2.locataire",
471:                        "label": "Locataire",
472:                        "value": {
473:                            "type": "boolean",
474:                            "value": true,
475:                            "polygon": [0,0,0,0,0,0,0,0],
476:                            "confidence": 1.0
477:                        }
478:                    },
479:                    {
480:                        "id": "situation_logement_demandeur2.procedure_expulsion",
481:                        "label": "Procédure d'expulsion",
482:                        "value": {
483:                            "type": "boolean",
484:                            "value": true,
485:                            "polygon": [0,0,0,0,0,0,0,0],
486:                            "confidence": 1.0
487:                        }
488:                    }
489:                ]
490:            },
491:            {
492:                "id": "situation_logement_co_demandeur2",
493:                "label": "Situation logement co demandeur 2",
494:                "kv_pairs": [
495:                    {
496:                        "id": "situation_logement_co_demandeur2.locataire",
497:                        "label": "Locataire",
498:                        "value": {
499:                            "type": "boolean",
500:                            "value": true,
501:                            "polygon": [0,0,0,0,0,0,0,0],
502:                            "confidence": 1.0
503:                        }
504:                    },
505:                    {
506:                        "id": "situation_logement_co_demandeur2.procedure_expulsion",
507:                        "label": "Procédure d'expulsion",
508:                        "value": {
509:                            "type": "boolean",
510:                            "value": true,
511:                            "polygon": [0,0,0,0,0,0,0,0],
512:                            "confidence": 1.0
513:                        }
514:                    }
515:                ]
516:            }
517:        ]
518:    },
519:    {
520:        "page_number": 4,
521:        "width": 0,
522:        "height": 0,
523:        "sections": [
524:            {
525:                "id": "prestations_familiales",
526:                "label": "Prestations familiales",
527:                "kv_pairs": [
528:                    {
529:                        "group_id": "demandeur",
530:                        "id": "prestations_familiales.numero_allocataire_caf",
531:                        "label": "Numéro allocataire CAF",
532:                        "value": {
533:                            "type": "text",
534:                            "text": "1000001",
535:                            "polygon": [0,0,0,0,0,0,0,0],
536:                            "confidence": 1.0
537:                        }
538:                    },
539:                    {
540:                        "group_id": "demandeur",
541:                        "id": "prestations_familiales.numero_msa",
542:                        "label": "Numéro Mutualité Sociale Agricole",
543:                        "value": {
544:                            "type": "text",
545:                            "text": "12345678901",  // CONFLICT: p04 shows "12345678901"
546:                            "polygon": [0,0,0,0,0,0,0,0],
547:                            "confidence": 1.0
548:                        }
549:                    },
550:                    {
551:                        "group_id": "co_demandeur",
552:                        "id": "prestations_familiales.numero_allocataire_caf",
553:                        "label": "Numéro allocataire CAF",
554:                        "value": {
555:                            "type": "text",
556:                            "text": "2000002",
557:                            "polygon": [0,0,0,0,0,0,0,0],
558:                            "confidence": 1.0
559:                        }
560:                    },
561:                    {
562:                        "group_id": "co_demandeur",
563:                        "id": "prestations_familiales.numero_msa",
564:                        "label": "Numéro Mutualité Sociale Agricole",
565:                        "value": {
566:                            "type": "text",
567:                            "text": "98765432109",  // CONFLICT: p05 shows "98765432109"
568:                            "polygon": [0,0,0,0,0,0,0,0],
569:                            "confidence": 1.0
570:                        }
571:                    }
572:                ]
573:            },
574:            {
575:                "id": "situation_professionnelle_demandeur",
576:                "label": "Situation professionnelle demandeur",
577:                "kv_pairs": [
578:                    {
579:                        "id": "situation_professionnelle_demandeur.profession",
580:                        "label": "Profession",
581:                        "value": null
582:                    },
583:                    {
584:                        "group_id": "categorie",
585:                        "id": "situation_professionnelle_demandeur.agriculteur",
586:                        "label": "Agriculteur",
587:                        "value": {
588:                            "type": "boolean",
589:                            "value": false,
590:                            "polygon": [0,0,0,0,0,0,0,0],
591:                            "confidence": 1.0
592:                        }
593:                    },
594:                    {
595:                        "group_id": "categorie",
596:                        "id": "situation_professionnelle_demandeur.profession_intermediaire",
597:                        "label": "Profession intermédiaire",
598:                        "value": {
599:                            "type": "boolean",
600:                            "value": true,
601:                            "polygon": [0,0,0,0,0,0,0,0],
602:                            "confidence": 1.0
603:                        }
604:                    },
605:                    {
606:                        "group_id": "situation_actuelle",
607:                        "id": "situation_professionnelle_demandeur.cdi",
608:                        "label": "CDI",
609:                        "value": {
610:                            "type": "boolean",
611:                            "value": true,
612:                            "polygon": [0,0,0,0,0,0,0,0],
613:                            "confidence": 1.0
614:                        }
615:                    },
616:                    {
617:                        "id": "situation_professionnelle_demandeur.depuis",
618:                        "label": "Depuis",
619:                        "value": {
620:                            "type": "date",
621:                            "raw_text": "03/11/2012",
622:                            "value": "2012-11-03",
623:                            "polygon": [0,0,0,0,0,0,0,0],
624:                            "confidence": 1.0
625:                        }
626:                    }
627:                ]
628:            },
629:            {
630:                "id": "situation_professionnelle_co_demandeur",
631:                "label": "Situation professionnelle co-demandeur",
632:                "kv_pairs": [
633:                    {
634:                        "id": "situation_professionnelle_co_demandeur.profession",
635:                        "label": "Profession",
636:                        "value": null
637:                    },
638:                    {
639:                        "group_id": "categorie",
640:                        "id": "situation_professionnelle_co_demandeur.cadre",
641:                        "label": "Cadre",
642:                        "value": {
643:                            "type": "boolean",
644:                            "value": true,
645:                            "polygon": [0,0,0,0,0,0,0,0],
646:                            "confidence": 1.0
647:                        }
648:                    },
649:                    {
650:                        "group_id": "situation_actuelle",
651:                        "id": "situation_professionnelle_co_demandeur.cdi",
652:                        "label": "CDI",
653:                        "value": {
654:                            "type": "boolean",
655:                            "value": true,
656:                            "polygon": [0,0,0,0,0,0,0,0],
657:                            "confidence": 1.0
658:                        }
659:                    },
660:                    {
661:                        "id": "situation_professionnelle_co_demandeur.depuis",
662:                        "label": "Depuis",
663:                        "value": {
664:                            "type": "date",
665:                            "raw_text": "03/11/1997",
666:                            "value": "1997-11-03",
667:                            "polygon": [0,0,0,0,0,0,0,0],
668:                            "confidence": 1.0
669:                        }
670:                    }
671:                ]
672:            },
673:            {
674:                "id": "travailleur_social",
675:                "label": "Travailleur social",
676:                "kv_pairs": [
677:                    {
678:                        "id": "travailleur_social.nom_organisme",
679:                        "label": "Nom de l'organisme",
680:                        "value": null
681:                    },
682:                    {
683:                        "id": "travailleur_social.adresse",
684:                        "label": "Adresse",
685:                        "value": null
686:                    },
687:                    {
688:                        "id": "travailleur_social.telephone",
689:                        "label": "Téléphone",
690:                        "value": null
691:                    },
692:                    {
693:                        "id": "travailleur_social.courriel",
694:                        "label": "Courriel",
695:                        "value": null
696:                    }
697:                ]
698:            }
699:        ]
700:    },
701:    {
702:        "page_number": 5,
703:        "width": 0,
704:        "height": 0,
705:        "sections": [
706:            {
707:                "id": "ressources_mensuelles_demandeur",
708:                "label": "Montant des ressources mensuelles - Demandeur",
709:                "kv_pairs": [
710:                    {
711:                        "id": "ressources_mensuelles_demandeur.salaire_net",
712:                        "label": "Salaire net",
713:                        "value": {
714:                            "type": "number",
715:                            "raw_text": "1888.50",
716:                            "value": 1888.5,
717:                            "polygon": [0,0,0,0,0,0,0,0],
718:                            "confidence": 1.0
719:                        }
720:                    },
721:                    {
722:                        "id": "ressources_mensuelles_demandeur.retraite",
723:                        "label": "Pension de retraite",
724:                        "value": null
725:                    },
726:                    {
727:                        "group_id": "autre",
728:                        "id": "ressources_mensuelles_demandeur.autre_type",
729:                        "label": "Autre ressource - type",
730:                        "value": null
731:                    },
732:                    {
733:                        "group_id": "autre",
734:                        "id": "ressources_mensuelles_demandeur.autre_montant",
735:                        "label": "Autre ressource - montant",
736:                        "value": null
737:                    },
738:                    {
739:                        "id": "ressources_mensuelles_demandeur.sans_ressources",
740:                        "label": "Sans ressources",
741:                        "value": {
742:                            "type": "boolean",
743:                            "value": false,
744:                            "polygon": [0,0,0,0,0,0,0,0],
745:                            "confidence": 1.0
746:                        }
747:                    }
748:                ]
749:            },
750:            {
751:                "id": "ressources_charges_logement_demandeur",
752:                "label": "Montant des charges - Logement - Demandeur",
753:                "kv_pairs": [
754:                    {
755:                        "id": "ressources_charges_logement_demandeur.loyer_hors_charges",
756:                        "label": "Loyer hors charges",
757:                        "value": null
758:                    },
759:                    {
760:                        "id": "ressources_charges_logement_demandeur.loyer_toutes_charges",
761:                        "label": "Loyer toutes charges comprises",
762:                        "value": null
763:                    },
764:                    {
765:                        "id": "ressources_charges_logement_demandeur.chauffage",
766:                        "label": "Frais de chauffage",
767:                        "value": null
768:                    },
769:                    {
770:                        "id": "ressources_charges_logement_demandeur.frais_maison_retraite",
771:                        "label": "Frais maison de retraite",
772:                        "value": null
773:                    },
774:                    {
775:                        "group_id": "autre",
776:                        "id": "ressources_charges_logement_demandeur.autre_type",
777:                        "label": "Autre charge logement - type",
778:                        "value": null
779:                    },
780:                    {
781:                        "group_id": "autre",
782:                        "id": "ressources_charges_logement_demandeur.autre_montant",
783:                        "label": "Autre charge logement - montant",
784:                        "value": null
785:                    }
786:                ]
787:            },
788:            {
789:                "id": "ressources_charges_impots_demandeur",
790:                "label": "Montant des charges - Impôts - Demandeur",
791:                "kv_pairs": [
792:                    {
793:                        "id": "ressources_charges_impots_demandeur.impots_revenu",
794:                        "label": "Impôts sur le revenu",
795:                        "value": null
796:                    },
797:                    {
798:                        "id": "ressources_charges_impots_demandeur.taxe_fonciere",
799:                        "label": "Taxe foncière",
800:                        "value": null
801:                    },
802:                    {
803:                        "group_id": "autre",
804:                        "id": "ressources_charges_impots_demandeur.autre_type",
805:                        "label": "Autre impôt - type",
806:                        "value": null
807:                    },
808:                    {
809:                        "group_id": "autre",
810:                        "id": "ressources_charges_impots_demandeur.autre_montant",
811:                        "label": "Autre impôt - montant",
812:                        "value": null
813:                    }
814:                ]
815:            },
816:            {
817:                "id": "ressources_charges_autres_demandeur",
818:                "label": "Montant des charges - Autres - Demandeur",
819:                "kv_pairs": [
820:                    {
821:                        "id": "ressources_charges_autres_demandeur.mutuelle",
822:                        "label": "Mutuelle",
823:                        "value": null
824:                    },
825:                    {
826:                        "id": "ressources_charges_autres_demandeur.frais_transport",
827:                        "label": "Frais de transport",
828:                        "value": null
829:                    },
830:                    {
831:                        "id": "ressources_charges_autres_demandeur.pension_alimentaire",
832:                        "label": "Pension alimentaire",
833:                        "value": null
834:                    },
835:                    {
836:                        "id": "ressources_charges_autres_demandeur.frais_garde",
837:                        "label": "Frais de garde",
838:                        "value": null
839:                    },
840:                    {
841:                        "id": "ressources_charges_autres_demandeur.frais_scolarite",
842:                        "label": "Frais de scolarité",
843:                        "value": null
844:                    },
845:                    {
846:                        "group_id": "autre",
847:                        "id": "ressources_charges_autres_demandeur.autre_type",
848:                        "label": "Autre charge - type",
849:                        "value": null
850:                    },
851:                    {
852:                        "group_id": "autre",
853:                        "id": "ressources_charges_autres_demandeur.autre_montant",
854:                        "label": "Autre charge - montant",
855:                        "value": null
856:                    }
857:                ]
858:            }
859:        ]
860:    },
861:    {
862:        "page_number": 6,
863:        "width": 0,
864:        "height": 0,
865:        "sections": [
866:            {
867:                "id": "vehicules",
868:                "label": "Véhicules",
869:                "kv_pairs": [
870:                    {
871:                        "group_id": "vehicule_1",
872:                        "id": "vehicules.proprietaire_demandeur",
873:                        "label": "Propriétaire - Demandeur",
874:                        "value": {
875:                            "type": "boolean",
876:                            "value": false,
877:                            "polygon": [0,0,0,0,0,0,0,0],
878:                            "confidence": 1.0
879:                        }
880:                    },
881:                    {
882:                        "group_id": "vehicule_1",
883:                        "id": "vehicules.proprietaire_co_demandeur",
884:                        "label": "Propriétaire - Co-demandeur",
885:                        "value": {
886:                            "type": "boolean",
887:                            "value": true,
888:                            "polygon": [0,0,0,0,0,0,0,0],
889:                            "confidence": 1.0
890:                        }
891:                    },
892:                    {
893:                        "group_id": "vehicule_1",
894:                        "id": "vehicules.type_vehicule",
895:                        "label": "Type de véhicule",
896:                        "value": {
897:                            "type": "text",
898:                            "text": "Vehicule Exemple 2015",
899:                            "polygon": [0,0,0,0,0,0,0,0],
900:                            "confidence": 1.0
901:                        }
902:                    },
903:                    {
904:                        "group_id": "vehicule_1",
905:                        "id": "vehicules.premiere_immatriculation",
906:                        "label": "Date de première immatriculation",
907:                        "value": null
908:                    },
909:                    {
910:                        "group_id": "vehicule_1",
911:                        "id": "vehicules.loa_lld_oui",
912:                        "label": "LOA / LLD - Oui",
913:                        "value": {
914:                            "type": "boolean",
915:                            "value": false,
916:                            "polygon": [0,0,0,0,0,0,0,0],
917:                            "confidence": 1.0
918:                        }
919:                    },
// GAP: lines 920–934 missing
935:                    {
936:                        "group_id": "vehicule_1",
937:                        "id": "vehicules.loa_lld_non",
938:                        "label": "LOA / LLD - Non",
939:                        "value": {
940:                            "type": "boolean",
941:                            "value": true,
942:                            "polygon": [0,0,0,0,0,0,0,0],
943:                            "confidence": 1.0
944:                        }
945:                    },
946:                    {
947:                        "group_id": "vehicule_1",
948:                        "id": "vehicules.valeur_estimee",
949:                        "label": "Valeur estimée",
950:                        "value": null
951:                    },
952:                    {
953:                        "group_id": "vehicule_2",
954:                        "id": "vehicules.proprietaire_demandeur",
955:                        "label": "Propriétaire - Demandeur",
956:                        "value": {
957:                            "type": "boolean",
958:                            "value": false,
959:                            "polygon": [0,0,0,0,0,0,0,0],
960:                            "confidence": 1.0
961:                        }
962:                    },
963:                    {
964:                        "group_id": "vehicule_2",
965:                        "id": "vehicules.proprietaire_co_demandeur",
966:                        "label": "Propriétaire - Co-demandeur",
967:                        "value": {
968:                            "type": "boolean",
969:                            "value": true,
970:                            "polygon": [0,0,0,0,0,0,0,0],
971:                            "confidence": 1.0
972:                        }
973:                    },
974:                    {
975:                        "group_id": "vehicule_2",
976:                        "id": "vehicules.type_vehicule",
977:                        "label": "Type de véhicule",
978:                        "value": {
979:                            "type": "text",
980:                            "text": "Vehicule Exemple 2015",
981:                            "polygon": [0,0,0,0,0,0,0,0],
982:                            "confidence": 1.0
983:                        }
984:                    },
985:                    {
986:                        "group_id": "vehicule_2",
987:                        "id": "vehicules.premiere_immatriculation",
988:                        "label": "Date de première immatriculation",
989:                        "value": null
990:                    },
991:                    {
992:                        "group_id": "vehicule_2",
993:                        "id": "vehicules.loa_lld_oui",
994:                        "label": "LOA / LLD - Oui",
995:                        "value": {
996:                            "type": "boolean",
997:                            "value": false,
998:                            "polygon": [0,0,0,0,0,0,0,0],
999:                            "confidence": 1.0
1000:                        }
1001:                    },
1002:                    {
1003:                        "group_id": "vehicule_2",
1004:                        "id": "vehicules.loa_lld_non",
1005:                        "label": "LOA / LLD - Non",
1006:                        "value": {
1007:                            "type": "boolean",
1008:                            "value": true,
1009:                            "polygon": [0,0,0,0,0,0,0,0],
1010:                            "confidence": 1.0
1011:                        }
1012:                    },
1013:                    {
1014:                        "group_id": "vehicule_2",
1015:                        "id": "vehicules.valeur_estimee",
1016:                        "label": "Valeur estimée",
1017:                        "value": null
1018:                    }
1019:                ]
1020:            }
1021:        ]
1022:    },
1023:    {
1024:        "page_number": 7,
1025:        "width": 0,
1026:        "height": 0,
1027:        "sections": [
1028:            {
1029:                "id": "patrimoine",
1030:                "label": "Patrimoine",
1031:                "kv_pairs": [
1032:                    {
1033:                        "id": "patrimoine.pas_de_patrimoine",
1034:                        "label": "Pas de patrimoine",
1035:                        "value": {
1036:                            "type": "boolean",
1037:                            "value": true,
1038:                            "polygon": [0,0,0,0,0,0,0,0],
1039:                            "confidence": 1.0
1040:                        }
1041:                    },
1042:                    {
1043:                        "group_id": "residence_principale",
1044:                        "id": "patrimoine.pret_en_cours_oui",
1045:                        "label": "Prêt en cours - Oui",
1046:                        "value": {
1047:                            "type": "boolean",
1048:                            "value": false,
1049:                            "polygon": [0,0,0,0,0,0,0,0],
1050:                            "confidence": 1.0
1051:                        }
1052:                    },
1053:                    {
1054:                        "group_id": "residence_principale",
1055:                        "id": "patrimoine.pret_en_cours_non",
1056:                        "label": "Prêt en cours - Non",
1057:                        "value": {
1058:                            "type": "boolean",
1059:                            "value": false,
1060:                            "polygon": [0,0,0,0,0,0,0,0],
1061:                            "confidence": 1.0
1062:                        }
1063:                    },
1064:                    {
1065:                        "group_id": "residence_principale",
1066:                        "id": "patrimoine.valeur",
1067:                        "label": "Valeur estimée",
1068:                        "value": null
1069:                    },
1070:                    {
1071:                        "group_id": "residence_principale",
1072:                        "id": "patrimoine.indivision_oui",
1073:                        "label": "Indivision - Oui",
1074:                        "value": {
1075:                            "type": "boolean",
1076:                            "value": false,
1077:                            "polygon": [0,0,0,0,0,0,0,0],
1078:                            "confidence": 1.0
1079:                        }
1080:                    },
1081:                    {
1082:                        "group_id": "residence_principale",
1083:                        "id": "patrimoine.indivision_non",
1084:                        "label": "Indivision - Non",
1085:                        "value": {
1086:                            "type": "boolean",
1087:                            "value": false,
1088:                            "polygon": [0,0,0,0,0,0,0,0],
1089:                            "confidence": 1.0
1090:                        }
1091:                    },
1092:                    {
1093:                        "group_id": "residence_principale",
1094:                        "id": "patrimoine.proprietaire_demandeur",
1095:                        "label": "Propriétaire demandeur",
1096:                        "value": {
1097:                            "type": "boolean",
1098:                            "value": false,
1099:                            "polygon": [0,0,0,0,0,0,0,0],
1100:                            "confidence": 1.0
1101:                        }
1102:                    },
1103:                    {
1104:                        "group_id": "residence_principale",
1105:                        "id": "patrimoine.proprietaire_co_demandeur",
1106:                        "label": "Propriétaire co-demandeur",
1107:                        "value": {
1108:                            "type": "boolean",
1109:                            "value": false,
1110:                            "polygon": [0,0,0,0,0,0,0,0],
1111:                            "confidence": 1.0
1112:                        }
1113:                    },
1114:                    {
1115:                        "group_id": "autre_immo_1",
1116:                        "id": "patrimoine.precisez",
1117:                        "label": "Autre bien immobilier - Précisez",
1118:                        "value": null
1119:                    },
1120:                    {
1121:                        "group_id": "autre_immo_2",
1122:                        "id": "patrimoine.precisez",
1123:                        "label": "Autre bien immobilier - Précisez",
1124:                        "value": null
1125:                    },
1126:                    {
1127:                        "group_id": "terrain",
1128:                        "id": "patrimoine.valeur",
1129:                        "label": "Valeur terrain",
1130:                        "value": null
1131:                    },
1132:                    {
1133:                        "group_id": "caravane",
1134:                        "id": "patrimoine.valeur",
1135:                        "label": "Valeur caravane",
1136:                        "value": null
1137:                    },
1138:                    {
1139:                        "group_id": "garage",
1140:                        "id": "patrimoine.valeur",
1141:                        "label": "Valeur garage",
1142:                        "value": null
1143:                    },
1144:                    {
1145:                        "group_id": "bijoux",
1146:                        "id": "patrimoine.valeur",
1147:                        "label": "Valeur des bijoux",
1148:                        "value": null
1149:                    },
1150:                    {
1151:                        "group_id": "bateau",
1152:                        "id": "patrimoine.valeur",
1153:                        "label": "Valeur bateau",
1154:                        "value": null
1155:                    }
1156:                ]
1157:            }
1158:        ]
1159:    },
1160:    {
1161:        "page_number": 8,
1162:        "width": 0,
1163:        "height": 0,
1164:        "sections": [
1165:            {
1166:                "id": "endettement",
1167:                "label": "État de l'endettement",
1168:                "kv_pairs": [
1169:                    {
1170:                        "group_id": "dette_1",
1171:                        "id": "endettement.logement",
1172:                        "label": "Dette logement",
1173:                        "value": {
1174:                            "type": "boolean",
1175:                            "value": false,
1176:                            "polygon": [0,0,0,0,0,0,0,0],
1177:                            "confidence": 1.0
1178:                        }
1179:                    },
1180:                    {
1181:                        "group_id": "dette_1",
1182:                        "id": "endettement.impots",
1183:                        "label": "Dette impôts",
1184:                        "value": {
1185:                            "type": "boolean",
1186:                            "value": false,
1187:                            "polygon": [0,0,0,0,0,0,0,0],
1188:                            "confidence": 1.0
1189:                        }
1190:                    },
1191:                    {
1192:                        "group_id": "dette_1",
1193:                        "id": "endettement.sante_education",
1194:                        "label": "Dette santé / éducation",
1195:                        "value": {
1196:                            "type": "boolean",
1197:                            "value": false,
1198:                            "polygon": [0,0,0,0,0,0,0,0],
1199:                            "confidence": 1.0
1200:                        }
1201:                    },
1202:                    {
1203:                        "group_id": "dette_1",
1204:                        "id": "endettement.charges_courantes",
1205:                        "label": "Charges courantes",
1206:                        "value": {
1207:                            "type": "boolean",
1208:                            "value": false,
1209:                            "polygon": [0,0,0,0,0,0,0,0],
1210:                            "confidence": 1.0
1211:                        }
1212:                    },
1213:                    {
1214:                        "group_id": "dette_1",
1215:                        "id": "endettement.pension_alimentaire",
1216:                        "label": "Pension alimentaire",
1217:                        "value": {
1218:                            "type": "boolean",
1219:                            "value": false,
1220:                            "polygon": [0,0,0,0,0,0,0,0],
1221:                            "confidence": 1.0
1222:                        }
1223:                    },
1224:                    {
1225:                        "group_id": "dette_1",
1226:                        "id": "endettement.amendes",
1227:                        "label": "Amendes",
1228:                        "value": {
1229:                            "type": "boolean",
1230:                            "value": false,
1231:                            "polygon": [0,0,0,0,0,0,0,0],
1232:                            "confidence": 1.0
1233:                        }
1234:                    },
1235:                    {
1236:                        "group_id": "dette_1",
1237:                        "id": "endettement.dettes_frauduleuses",
1238:                        "label": "Dettes frauduleuses",
1239:                        "value": {
1240:                            "type": "boolean",
1241:                            "value": false,
1242:                            "polygon": [0,0,0,0,0,0,0,0],
1243:                            "confidence": 1.0
1244:                        }
1245:                    },
1246:                    {
1247:                        "group_id": "dette_1",
1248:                        "id": "endettement.dettes_sociales",
1249:                        "label": "Dettes sociales",
1250:                        "value": {
1251:                            "type": "boolean",
1252:                            "value": false,
1253:                            "polygon": [0,0,0,0,0,0,0,0],
1254:                            "confidence": 1.0
1255:                        }
1256:                    },
1257:                    {
1258:                        "group_id": "dette_1",
1259:                        "id": "endettement.autres",
1260:                        "label": "Autres dettes",
1261:                        "value": {
1262:                            "type": "boolean",
1263:                            "value": false,
1264:                            "polygon": [0,0,0,0,0,0,0,0],
1265:                            "confidence": 1.0
1266:                        }
1267:                    },
1268:                    {
1269:                        "group_id": "dette_1",
1270:                        "id": "endettement.nom_creancier",
1271:                        "label": "Nom du créancier",
1272:                        "value": null
1273:                    },
1274:                    {
1275:                        "group_id": "dette_1",
1276:                        "id": "endettement.adresse_creancier",
1277:                        "label": "Adresse du créancier",
1278:                        "value": null
1279:                    },
1280:                    {
1281:                        "group_id": "dette_1",
1282:                        "id": "endettement.reference",
1283:                        "label": "Référence",
1284:                        "value": null
1285:                    },
1286:                    {
1287:                        "group_id": "dette_1",
1288:                        "id": "endettement.montant",
1289:                        "label": "Montant de la dette",
1290:                        "value": null
1291:                    },
1292:                    {
1293:                        "group_id": "dette_1",
1294:                        "id": "endettement.poursuites_oui",
1295:                        "label": "Poursuites en cours - Oui",
1296:                        "value": {
1297:                            "type": "boolean",
1298:                            "value": false,
1299:                            "polygon": [0,0,0,0,0,0,0,0],
1300:                            "confidence": 1.0
1301:                        }
1302:                    },
1303:                    {
1304:                        "group_id": "dette_1",
1305:                        "id": "endettement.poursuites_non",
1306:                        "label": "Poursuites en cours - Non",
1307:                        "value": {
1308:                            "type": "boolean",
1309:                            "value": true,
1310:                            "polygon": [0,0,0,0,0,0,0,0],
1311:                            "confidence": 1.0
1312:                        }
1313:                    },
1314:                    {
1315:                        "group_id": "dette_2",
1316:                        "id": "endettement.logement",
1317:                        "label": "Dette logement",
1318:                        "value": {
1319:                            "type": "boolean",
1320:                            "value": false,
1321:                            "polygon": [0,0,0,0,0,0,0,0],
1322:                            "confidence": 1.0
1323:                        }
1324:                    },
1325:                    {
1326:                        "group_id": "dette_2",
1327:                        "id": "endettement.impots",
1328:                        "label": "Dette impôts",
1329:                        "value": {
1330:                            "type": "boolean",
1331:                            "value": false,
1332:                            "polygon": [0,0,0,0,0,0,0,0],
1333:                            "confidence": 1.0
1334:                        }
1335:                    },
// GAP: lines 1336–1347 missing (dette_2 boolean fields)
1348:                    {
1349:                        "group_id": "dette_2",
1350:                        "id": "endettement.nom_creancier",
1351:                        "label": "Nom du créancier",
1352:                        "value": null
1353:                    },
1354:                    {
1355:                        "group_id": "dette_2",
1356:                        "id": "endettement.montant",
1357:                        "label": "Montant de la dette",
1358:                        "value": null
1359:                    },
1360:                    {
1361:                        "group_id": "dette_2",
1362:                        "id": "endettement.poursuites_oui",
1363:                        "label": "Poursuites en cours - Oui",
1364:                        "value": {
1365:                            "type": "boolean",
1366:                            "value": false,
1367:                            "polygon": [0,0,0,0,0,0,0,0],
1368:                            "confidence": 1.0
1369:                        }
1370:                    },
1371:                    {
1372:                        "group_id": "dette_2",
1373:                        "id": "endettement.poursuites_non",
1374:                        "label": "Poursuites en cours - Non",
1375:                        "value": {
1376:                            "type": "boolean",
1377:                            "value": true,
1378:                            "polygon": [0,0,0,0,0,0,0,0],
1379:                            "confidence": 1.0
1380:                        }
1381:                    }
1382:                ]
1383:            }
1384:        ]
// file ends here (closing braces for root object/array not visible but implied)
```

---

## File 2: `scripts/download_swagger.ps1` (lines 1–9, complete)

```powershell
1  $version = "5.17.14"
2  $base = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@$version"
3  $out = "src\adam_api\static"
4  
5  New-Item -ItemType Directory -Force -Path $out
6  Invoke-WebRequest "$base/swagger-ui-bundle.js" -OutFile "$out\swagger-ui-bundle.js"
7  Invoke-WebRequest "$base/swagger-ui.css"        -OutFile "$out\swagger-ui.css"
8  
9  Write-Host "Swagger UI $version telecharge" -ForegroundColor Green
```

---

## File 3: `scripts/run-checks.ps1` (lines 1–51, complete)

```powershell
1  <#
2  .SYNOPSIS
3      Runs Python formatting, linting, security checks, and tests in the optimal order.
4  #>
5  
6  $ErrorActionPreference = "Stop"
7  
8  Function Invoke-Check {
9      param (
10         [string]$Name,
11         [scriptblock]$Command
12     )
13 
14     Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
15     Write-Host "Running: $Name" -ForegroundColor Yellow
16     Write-Host "------------------------------------------------------------" -ForegroundColor Cyan
17 
18     # Execute the command
19     & $Command
20 
21     # Check the exit code of the Python process
22     if ($LASTEXITCODE -ne 0) {
23         Write-Host "`n[X] ERROR: $Name failed with exit code $LASTEXITCODE.`n" -ForegroundColor Red
24         Write-Host "Aborting subsequent checks.`n" -ForegroundColor Red
25         exit $LASTEXITCODE
26     }
27 
28     Write-Host "[OK] $Name completed successfully.`n" -ForegroundColor Green
29 }
30 
31 # 1. Format imports
32 Invoke-Check "isort (Import Sorting)" { python -m isort src\ }
33 
34 # 2. Format code
35 Invoke-Check "black (Code Formatting)" { python -m black src\ }
36 
37 # 3. Static type checking
38 Invoke-Check "mypy (Type Checking)" { python -m mypy src\ --strict --ignore-missing-imports }
39 
40 # 4. Linting
41 Invoke-Check "pylint (Code linting)" { python -m pylint .\src\ }
42 
43 # 5. Security Scanning
44 Invoke-Check "bandit (Security Scan)" { python -m bandit -ll -r src\ }
45 
46 # 6. Unit Tests & Coverage
47 Invoke-Check "pytest (Tests & Coverage)" { python -m pytest --cov=src --cov-report=term-missing }
48 
49 Write-Host "-------------------------------------------" -ForegroundColor Green
50 Write-Host "All checks passed successfully!" -ForegroundColor Green
51 Write-Host "-------------------------------------------" -ForegroundColor Green
```

---

## File 4: `scripts/run_dev.py` (lines 1–20, complete)

```python
1  """
2  Point d'entrée DEV uniquement, ne jamais utiliser en STAGING/PROD.
3  
4  Usage :
5      python scripts/run_dev.py
6  """
7  import uvicorn
8  
9  from adam_api.core.config import settings
10 
11 if __name__ == "__main__":
12     uvicorn.run(
13         "adam_api.main:app",
14         host="127.0.0.1",
15         port=settings.api_port,
16         reload=True,
17         log_config=None,
18         access_log=False,
19     )
20 
```

---

## File 5: `scripts/seed.py` (lines 1–457, complete)

```python
1  """
2  scripts/seed.py
3  ----------
4  Seed unifie de la base ADAM.
5  
6  Deux modes :
7      - Sans JSON : donnees de test formulaire demo hardcodees
8      - Avec JSON : schema et champs derives d'un fichier format formulaire v0.3
9  
10 Usage :
11     python scripts/seed.py
12     python scripts/seed.py --reset
13     python scripts/seed.py --json form_demo_v0.3.json
14     python scripts/seed.py --json form_demo_v0.3.json --reset
15 """
16 
17 import argparse
18 import asyncio
19 import hashlib
20 import json
21 import sys
22 from pathlib import Path
23 from typing import Dict, List, Optional, Tuple
24 
25 sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
26 
27 from sqlalchemy import text
28 from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
29 
30 from adam_core.core.config import CoreSettings
31 from adam_core.db.session import create_tables, get_engine, init_engine
32 from adam_core.enums.ocr import OcrProvider, StorageMode
33 from adam_core.enums.roles import UserRole
34 from adam_core.enums.status import (
35     DatasetStatus,
36     DocumentFieldStatus,
37     DocumentStatus,
38     FieldValueType,
39     ProjectStatus,
40     UserStatus,
41 )
42 from adam_core.models import (
43     Dataset,
44     DocSchema,
45     Document,
46     DocumentField,
47     FieldSpec,
48     File,
49     OcrResult,
50     Organisation,
51     Project,
52     User,
53     UserProject,
54 )
55 
56 settings = CoreSettings()
57 
58 SEPARATOR = "-" * 55
59 
60 
61 # Reset
62 
63 
64 async def reset_db(session: AsyncSession) -> None:
65     print(" Reset de la base...")
66     tables = [
67         "document_field", "ocr_result", "document", "file",
68         "dataset", "field_spec", "doc_schema",
69         "user_project", "project", "user", "organisation",
70     ]
71     for table in tables:
72         await session.execute(text(f'TRUNCATE TABLE "{table}" CASCADE'))
73     await session.commit()
74     print(" Tables videes")
75 
76 
77 # Infrastructure commune
78 
79 
80 async def seed_infrastructure(session: AsyncSession) -> Tuple:
81     print("\n [1/3] Organisations...")
82     org_alpha = Organisation(name="Org Alpha", slug="org_alpha")
83     org_beta = Organisation(name="Org Beta", slug="org_beta")
84     session.add_all([org_alpha, org_beta])
85     await session.flush()
86     print(f"        {org_alpha}")
87     print(f"        {org_beta}")
88 
89     print(" [2/3] Users...")
90     admin = User(
91         organisation_id=org_beta.id,
92         email="admin@example.com",
93         full_name="Admin ADAM",
94         matricule="MAT00001",
95         status=UserStatus.ACTIVE.value,
96     )
97     operator = User(
98         organisation_id=org_beta.id,
99         email="operateur@example.com",
100        full_name="Operateur ADAM",
101        matricule="MAT00002",
102        status=UserStatus.ACTIVE.value,
103    )
104    session.add_all([admin, operator])
105    await session.flush()
106    print(f"        {admin}")
107    print(f"        {operator}")
108
109    print(" [3/3] Project + UserProjects...")
110    project = Project(
111        organisation_id=org_beta.id,
112        name="Projet Demo Formulaires",
113        description="Labellisation de formulaires administratifs demo",
114        status=ProjectStatus.ACTIVE.value,
115    )
116    session.add(project)
117    await session.flush()
118
119    session.add_all([
120        UserProject(user_id=admin.id, project_id=project.id, role=UserRole.ADMIN.value),
121        UserProject(user_id=operator.id, project_id=project.id, role=UserRole.OPERATOR.value),
122    ])
123    await session.flush()
124    print(f"        {project}")
125
126    return org_beta, admin, operator, project
127
128
129# Mode 1 : Donnees hardcodees
130
131
132HARDCODED_FIELD_SPECS = [
133    ("demandeur", "Demandeur", "demandeur.nom", "Nom de naissance", FieldValueType.TEXT.value, 1),
134    ("demandeur", "Demandeur", "demandeur.prenom", "Prenom", FieldValueType.TEXT.value, 1),
135    ("demandeur", "Demandeur", "demandeur.date_naissance", "Date de naissance", FieldValueType.DATE.value, 1),
136    ("demandeur", "Demandeur", "demandeur.civilite_m", "Monsieur", FieldValueType.BOOLEAN.value, 1),
137    ("demandeur", "Demandeur", "demandeur.civilite_mme", "Madame", FieldValueType.BOOLEAN.value, 1),
138    ("bien", "Bien", "bien.adresse", "Adresse du bien", FieldValueType.TEXT.value, 1),
139    ("bien", "Bien", "bien.valeur", "Valeur du bien (EUR)", FieldValueType.NUMBER.value, 1),
140    ("bien", "Bien", "bien.superficie", "Superficie (m2)", FieldValueType.NUMBER.value, 1),
141    ("creance", "Creance", "creance.montant", "Montant creance", FieldValueType.NUMBER.value, 1),
142    ("creance", "Creance", "creance.date_echeance", "Date d'echeance", FieldValueType.DATE.value, 1),
143]
144
145HARDCODED_OCR_VALUES: Dict = {
146    "demandeur.nom":                 ("NOM01",                      0.98, [182,282,298,182,298,168,82,168]),
147    "demandeur.prenom":              ("P02",                        0.97, [82,142,288,142,288,168,82,168]),
148    "demandeur.date_naissance":      ("1980-01-06",                  0.95, [82,182,218,182,218,208,82,208]),
149    "demandeur.civilite_m":          ("true",                        1.00, [82,222,118,222,118,238,82,238]),
150    "demandeur.civilite_mme":        ("false",                       1.00, [132,222,178,222,178,238,132,238]),
151    "bien.adresse":                 ("1 rue Demo 00000 Villedemo", 0.91, [82,102,498,102,498,128,82,128]),
152    "bien.valeur":                  ("450000",                      0.88, [82,142,298,142,298,168,82,168]),
153    "bien.superficie":              ("85",                          0.93, [322,142,448,142,448,168,322,168]),
154    "creance.montant":              ("320000",                      0.90, [82,222,298,222,298,248,82,248]),
155    "creance.date_echeance":        ("2046-01-15",                  0.94, [322,222,498,222,498,248,322,248]),
156}
157
158HARDCODED_RAW_JSON = {
159    "format_version": "0.3",
160    "document_id": "form_demo_001",
161    "coordinate_unit": "pixel",
162    "page_count": 2,
163    "metadata": {"ocr": {"provider": "PULSAR", "processed_at": "2026-01-15T10:00:00Z"}},
164    "pages": [],
165}
166
167
168async def seed_hardcoded(session: AsyncSession, project: Project) -> None:
169    print("\n --- Mode : donnees hardcodees (Formulaire Demo v2) ---")
170
171    print(" [4/8] DocSchema...")
172    schema = DocSchema(
173        project_id=project.id,
174        version=2,
175        name="Schema Formulaire Demo v2",
176        document_type="FORM_DEMO_02",
177    )
178    session.add(schema)
179    await session.flush()
180    print(f"        {schema}")
181
182    print(" [5/8] FieldSpecs...")
183    field_specs = []
184    for i, (sec_id, sec_label, key, label, ftype, page, required, polygon) in enumerate(HARDCODED_FIELD_SPECS):
185        fs = FieldSpec(
186            schema_id=schema.id, page=page,
187            section_id=sec_id, section_label=sec_label,
188            field_key=key, display_label=label,
189            value_type=ftype, required=required,
190            display_order=i, polygon=polygon,
191        )
192        field_specs.append(fs)
193
194    session.add_all(field_specs)
195    await session.flush()
196    print(f"    --- {len(field_specs)} FieldSpecs crees")
197
198    await _seed_dataset_to_fields(
199        session, project, schema, field_specs,
200        file_path="/pvc/org-beta/forms/2026_01/2026_01_15_1321/form_demo_001.pdf",
201        file_name="form_demo_001.pdf",
202        raw_json=HARDCODED_RAW_JSON,
203        ocr_values=HARDCODED_OCR_VALUES,
204        document_id_str="form_demo_001",
205        step_offset=6,
206    )
207
208
209# Mode 2 : Depuis JSON formulaire
210
211
212async def seed_from_form_json(
213    session: AsyncSession, project: Project, json_path: Path
214) -> None:
215    from adam_core.schemas.interface_contract import FormDocument
216
217    print(f"\n --- Mode : FORM JSON ({json_path.name}) ---")
218
219    with open(json_path, encoding="utf-8") as f:
220        json_raw = json.load(f)
221
222    form_doc = FormDocument.model_validate(json_raw)
223    print(f" JSON valide : {form_doc.page_count} pages, document_id={form_doc.document_id}")
224
225    print(" [4/8] DocSchema...")
226    schema = DocSchema(
227        project_id=project.id,
228        version=1,
229        name="Formulaire Demo",
230        document_type="FORM_DEMO_01",
231    )
232    session.add(schema)
233    await session.flush()
234    print(f"        {schema}")
235
236    print(" [5/8] FieldSpecs (dérivés du JSON)...")
237    specs_data = form_doc.extract_field_specs()
238    field_spec_index: Dict = {}
239    field_specs = []
240
241    for spec in specs_data:
242        fs = FieldSpec(
243            schema_id=schema.id,
244            page=spec["page"],
245            section_id=spec["section_id"],
246            section_label=spec["section_label"],
247            field_key=spec["field_key"],
248            display_label=spec["display_label"],
249            value_type=spec["value_type"],
250            required=spec["required"],
251            display_order=spec["display_order"],
252            polygon=spec["polygon"],
253        )
254        field_specs.append(fs)
255        session.add(fs)
256        await session.flush()
257        field_spec_index[(spec["section_id"], spec["field_key"])] = fs
258
259    print(f"        {len(field_specs)} FieldSpecs créés depuis {form_doc.page_count} pages")
260
261    print(" [6/8] Dataset...")
262    dataset = Dataset(
263        project_id=project.id, schema_id=schema.id,
264        name="Lot Formulaire Demo - Seed",
265        ocr_provider=OcrProvider.PULSAR.value,
266        status=DatasetStatus.ACTIVE.value,
267        required_operators=2,
268        configs={"confidence_threshold": 0.8},
269    )
270    session.add(dataset)
271    await session.flush()
272    print(f"        {dataset=}")
273
274    print(" [7/8] File + Document...")
275    json_bytes = json.dumps(json_raw, ensure_ascii=False).encode("utf-8")
276    sha256 = hashlib.sha256(json_bytes).hexdigest()
277
278    file_ = File(
279        file_path=f"/pvc/forms/demo/{form_doc.document_id}.pdf",
280        storage_type="pvc", mime_type="application/pdf",
281        page_count=form_doc.page_count,
282        file_size_bytes=len(json_bytes),
283        sha256_checksum=sha256,
284    )
285    session.add(file_)
286    await session.flush()
287
288    document = Document(
289        dataset_id=dataset.id, file_id=file_.id,
290        file_name=f"{form_doc.document_id}.pdf",
291        metadata={
292            "format_version": form_doc.format_version,
293            "document_id": form_doc.document_id,
294            "coordinate_unit": form_doc.coordinate_unit,
295        },
296        status=DocumentStatus.IN_PROGRESS.value,
297    )
298    session.add(document)
299    await session.flush()
300    print(f"        {file_}")
301    print(f"        {document}")
302
303    print("    [8/8] OcrResult + DocumentFields...")
304    ocr_result = OcrResult(
305        document_id=document.id, dataset_id=dataset.id,
306        storage_mode=StorageMode.JSONB.value,
307        raw_json=json_raw,
308    )
309    session.add(ocr_result)
310    await session.flush()
311
312    doc_fields = []
313    skipped = 0
314    for _, section, kv in form_doc.iter_kv_pairs():
315        fs = field_spec_index.get((section.id, kv.field_key))
316        if not fs:
317            skipped += 1
318            continue
319        doc_fields.append(DocumentField(
320            document_id=document.id, field_spec_id=fs.id,
321            group_id=kv.group_id,
322            ocr_value=kv.extracted_value, resolved_value=kv.extracted_value,
323            status=DocumentFieldStatus.PENDING.value,
324            ocr_confidence=kv.confidence, consensus_reached=False,
325            ocr_polygon=kv.polygon,
326        ))
327
328    session.add_all(doc_fields)
329    await session.flush()
330
331    print(f"            {len(doc_fields)} DocumentFields crees")
332    if skipped:
333        print(f"            {skipped} KVPairs ignores (fieldSpec manquant)")
334
335    print(f"\n Resume : {len(field_specs)} FieldSpecs, {len(doc_fields)} DocumentFields, {form_doc.page_count}")
336
337
338# Helper partagé
339
340
341async def _seed_dataset_to_fields(
342    session: AsyncSession,
343    project: Project,
344    schema: DocSchema,
345    field_specs: List[FieldSpec],
346    file_path: str,
347    file_name: str,
348    raw_json: dict,
349    ocr_values: Dict,
350    document_id_str: str,
351    step_offset: int,
352) -> None:
353    print(f"  [{step_offset}/8] Dataset...")
354    dataset = Dataset(
355        project_id=project.id, schema_id=schema.id,
356        name="Lot janvier 2024",
357        description="Premier lot de documents",
358        ocr_provider=OcrProvider.PULSAR.value,
359        status=DatasetStatus.ACTIVE.value,
360        required_operators=2,
361        configs={"confidence_threshold": 0.8, "export_format": "json_pdf"},
362    )
363    session.add(dataset)
364    await session.flush()
365    print(f"        {dataset}")
366
367    print(f"  [{step_offset + 1}/8] File + Document...")
368    json_bytes = json.dumps(raw_json, ensure_ascii=False).encode("utf-8")
369    sha256 = hashlib.sha256(json_bytes).hexdigest()
370
371    file_ = File(
372        file_path=file_path, storage_type="PVC",
373        mime_type="application/pdf", page_count=raw_json.get("page_count", 2),
374        file_size_bytes=len(json_bytes), sha256_checksum=sha256,
375    )
376    session.add(file_)
377    await session.flush()
378
379    document = Document(
380        dataset_id=dataset.id, file_id=file_.id, file_name=file_name,
381        metadata={"source": "PVC", "lot": "2024-01", "reception_date": "2024-01-15"},
382        status=DocumentStatus.IN_PROGRESS.value,
383    )
384    session.add(document)
385    await session.flush()
386    print(f"        {file_}")
387    print(f"        {document}")
388
389    print(f"  [{step_offset + 2}/8] OcrResult + DocumentFields...")
390    ocr_result = OcrResult(
391        document_id=document.id, dataset_id=dataset.id,
392        storage_mode=StorageMode.JSONB.value, raw_json=raw_json,
393    )
394    session.add(ocr_result)
395    await session.flush()
396
397    doc_fields = []
398    for fs in field_specs:
399        ocr_val, confidence, polygon = ocr_values.get(fs.field_key, (None, None, None))
400        doc_fields.append(DocumentField(
401            document_id=document.id, field_spec_id=fs.id, group_id=None,
402            ocr_value=ocr_val, resolved_value=ocr_val,
403            status=DocumentFieldStatus.PENDING.value,
404            ocr_confidence=confidence, consensus_reached=False, ocr_polygon=polygon,
405        ))
406    session.add_all(doc_fields)
407    await session.flush()
408    print(f"        {len(doc_fields)} DocumentFields crees")
409
410
411# Main
412
413
414async def main(reset: bool, json_path: Optional[Path]) -> None:
415    init_engine(settings.async_database_url, echo=False)
416    await create_tables()
417
418    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
419    async with factory() as session:
420        if reset:
421            await reset_db(session)
422
423        _, admin, operator, project = await seed_infrastructure(session)
424
425        if json_path:
426            await seed_from_form_json(session, project, json_path)
427        else:
428            await seed_hardcoded(session, project)
429
430        await session.commit()
431
432    await get_engine().dispose()
433    print("\n Seed termine avec succes")
434
435
436if __name__ == "__main__":
437    parser = argparse.ArgumentParser(description="Seed ADAM database")
438    parser.add_argument("--reset", action="store_true", help="Vide les tables avant de seeder")
439    parser.add_argument("--json", default=None, help="Chemin vers un fichier JSON format formulaire v0.3")
440    args = parser.parse_args()
441
442    json_path = None
443    if args.json:
444        json_path = Path(args.json)
445        if not json_path.exists():
446            json_path = Path(__file__).parent.parent / args.json
447        if not json_path.exists():
448            print(f"Fichier introuvable : {args.json}")
449            sys.exit(1)
450
451    print(SEPARATOR)
452    print("Seed de la base de donnees")
453    print(f" Mode : {'FORM JSON' if json_path else 'Donnees hardcodees'}")
454    print(SEPARATOR)
455    asyncio.run(main(reset=args.reset, json_path=json_path))
456    print(SEPARATOR)
457
```

---

## File 6: `scripts/test_connection.py` (lines 1–87, complete)

```python
1  """
2  Script standalone pour vérifier la connexion à PostgreSQL.
3  """
4  
5  import asyncio
6  import os
7  import sys
8  from pathlib import Path
9  
10 
11 # Chargement du .env
12 def load_env(env_path: Path = Path(".env")) -> None:
13     if not env_path.exists():
14         print(
15             f"[WARN] Fichier {env_path} introuvable : utilisation des variables système"
16         )
17         return
18     with env_path.open() as f:
19         for line in f:
20             line = line.strip()
21             if not line or line.startswith("#") or "=" not in line:
22                 continue
23             key, _, value = line.partition("=")
24             os.environ.setdefault(key.strip(), value.strip())
25 
26 
27 load_env()
28 
29 # Paramètres de connexion
30 DB_USER = os.getenv("POSTGRES_USER")
31 DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
32 DB_HOST = os.getenv("POSTGRES_HOST")
33 DB_PORT = int(os.getenv("POSTGRES_PORT"))
34 DB_NAME = os.getenv("POSTGRES_DB")
35 
36 
37 async def test_connection() -> bool:
38     try:
39         import asyncpg
40     except ImportError:
41         print("[ERROR] asyncpg n'est pas installé.")
42         return False
43 
44     url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
45     print(f"URL: {url}")
46     print(f"\n Tentative de connexion sur :")
47     print(f"  host={DB_HOST}  port={DB_PORT}  db={DB_NAME}  user={DB_USER}\n")
48 
49     try:
50         conn = await asyncpg.connect(
51             host=DB_HOST,
52             port=DB_PORT,
53             user=DB_USER,
54             password=DB_PASSWORD,
55             database=DB_NAME,
56             timeout=5,
57         )
58     except Exception as e:
59         print(f" [ÉCHEC] Impossible de se connecter :\n {type(e).__name__}: {e}")
60         print("\n Vérifications :")
61         print("  1. PostgreSQL est-il démarré ? (Services Windows -> postgresql-x64-14)")
62         print("  2. Le user 'adam' existe-t-il dans pgAdmin ?")
63         print("  3. La base 'adam_db' existe-t-elle avec owner='adam' ?")
64         print("  4. Les credentials dans .env sont-ils corrects ?")
65         return False
66 
67     # Requêtes de vérification
68     pg_version = await conn.fetchval("SELECT version()")
69     current_db = await conn.fetchval("SELECT current_database()")
70     current_user = await conn.fetchval("SELECT current_user")
71 
72     await conn.close()
73 
74     print(f" [OK] Connexion réussie !")
75     print(f" PostgreSQL : {pg_version.split(',')[0]}")
76     print(f" Base       : {current_db}")
77     print(f" Utilisateur: {current_user}")
78     return True
79 
80 
81 if __name__ == "__main__":
82     print("=" * 55)
83     print("Test de connexion PostgreSQL")
84     print("=" * 55)
85     success = asyncio.run(test_connection())
86     print("=" * 55)
87     sys.exit(0 if success else 1)
```

---

## Summary

- **Pds1 covers:** tail end of `form_demo_v0.3.json` (pages 4–8 of the form data) + all `scripts/` utility files
- **Critical missing data:** lines **1–465** of the JSON (document header, pages 1–3) — likely in another PDF/screenshot set
- **5 scripts are fully recoverable** from Pds1 alone
- **Package layout hints:** `src/adam_api/` (API), `src/adam_core/` (core/DB), `scripts/` (dev tooling)

[REDACTED]