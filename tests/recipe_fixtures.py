"""Complete reference recipe/process fixtures replacing the removed factory catalog.

The structure was frozen from the former ``BUILTIN_BASELINE_SEEDS`` /
``LAYER_PRESETS`` factory catalogs, but every fabrication parameter has been
replaced with obviously synthetic placeholder values (round rpm numbers, the
generic VV02 valve, 10 nm films, 5 mg solids, "Example solvent"). Passivation
solutions dissolve BOTH PEAI and EDADI powders in IPA, matching the lab's
chemistry. They are NOT real laboratory setpoints; tests only rely on the
values being structurally valid and internally consistent.
"""

from __future__ import annotations

import json

REFERENCE_DEVICE_RECIPE = json.loads(r'''
{
    "schema_version": 2,
    "setup_mode": "baseline",
    "junction_type": "single_junction",
    "perovskite_bandgap": "normal_bandgap",
    "tandem_type": null,
    "experimental_groups": [
        {
            "group_id": "control",
            "kind": "control",
            "name": "Control",
            "change_from_control": "Baseline fabrication procedure",
            "inherits_control": false,
            "adjustments": [],
            "substrate_count": null
        },
        {
            "group_id": "target-1",
            "kind": "target",
            "name": "Target 1",
            "change_from_control": "",
            "inherits_control": true,
            "adjustments": [
                {
                    "parameter": "device_recipe.substrate.width_mm",
                    "parameter_label": "Substrate · Width (mm)",
                    "control_value": "15",
                    "target_value": "25"
                }
            ],
            "layers": null,
            "substrate_count": null
        }
    ],
    "substrate": {
        "material": "ITO",
        "vendor": "Example vendor",
        "type_number": "ITO-15",
        "width_mm": 15.0,
        "length_mm": 15.0
    },
    "layers": [
        {
            "layer_type": "niox",
            "name": "NiOx",
            "preset_id": "niox_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "htl",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "NiOx solid",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "Example solvent",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        },
        {
            "layer_type": "sam",
            "name": "SAM",
            "preset_id": "sam_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "htl",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "SAM solid",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "Example solvent",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        },
        {
            "layer_type": "sio2_np",
            "name": "SiO₂ nanoparticle",
            "preset_id": "buried_interface_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "buried_interface_modifier",
            "solution": {
                "formulation_type": "diluted_dispersion",
                "solids": [],
                "solvents": [
                    {
                        "solvent": "Example solvent",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "SiO2 NP stock dispersion",
                "stock_volume_ml": 0.1
            }
        },
        {
            "layer_type": "perovskite",
            "name": "Perovskite",
            "preset_id": "perovskite_spin_v1",
            "process": null,
            "role": "perovskite",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "Perovskite solid",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "Example solvent",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        },
        {
            "layer_type": "peai",
            "name": "PEAI",
            "preset_id": "passivation_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "top_passivation",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "PEAI",
                        "weight_mg": 5.0
                    },
                    {
                        "chemical": "EDADI",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "IPA",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        },
        {
            "layer_type": "pcbm",
            "name": "PCBM",
            "preset_id": "pcbm_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "etl",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "PCBM solid",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "Example solvent",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        },
        {
            "layer_type": "c60",
            "name": "C60",
            "preset_id": "c60_evap_v1",
            "process": {
                "method": "thermal_evaporation",
                "rate_angstrom_per_s": 0.1,
                "thickness_nm": 10.0
            },
            "role": "etl",
            "solution": null
        },
        {
            "layer_type": "sno2",
            "name": "SnO2",
            "preset_id": "sno2_ald_v1",
            "process": {
                "cycles": 50,
                "method": "ald",
                "substrate_temperature_c": 60.0,
                "thickness_nm": 10.0
            },
            "role": "etl",
            "solution": null
        },
        {
            "layer_type": "ag",
            "name": "Ag",
            "preset_id": "ag_evap_v1",
            "process": {
                "method": "thermal_evaporation",
                "rate_angstrom_per_s": 0.1,
                "thickness_nm": 10.0
            },
            "role": "top_electrode",
            "solution": null
        }
    ]
}
''')

REFERENCE_DEPOSITION_PROCESS = json.loads(r'''
{
    "anneal_steps": [
        {
            "seconds": 45,
            "temperature_c": 55
        },
        {
            "seconds": 90,
            "temperature_c": 60
        }
    ],
    "gas_backfill_stages": [],
    "method": "spin_coating_vcd",
    "spin_steps": [
        {
            "acceleration_rpm_per_s": 100,
            "rpm": 1000,
            "seconds": 10
        }
    ],
    "vcd_stages": [
        {
            "pressure_pa": 900,
            "seconds": 10,
            "valve": "VV02"
        },
        {
            "pressure_pa": 600,
            "seconds": 10,
            "valve": "VV02"
        },
        {
            "pressure_pa": 300,
            "seconds": 10,
            "valve": "VV02"
        }
    ]
}
''')

# Minimal schema-valid layer dicts for preset API tests (complete values are
# not required here: preset storage validates perovskite processes only).
# Passivation solutions contain BOTH PEAI and EDADI powders in IPA.

SAM_LAYER = json.loads(r'''
{
    "layer_type": "sam",
    "name": "SAM",
    "preset_id": "sam_spin_v1",
    "process": {
        "anneal_steps": [
            {
                "seconds": 45,
                "temperature_c": 55
            }
        ],
        "method": "spin_coating",
        "spin_steps": [
            {
                "acceleration_rpm_per_s": 100,
                "rpm": 1000,
                "seconds": 10
            }
        ]
    },
    "role": "htl",
    "solution": {
        "formulation_type": "weighed_solids",
        "solids": [
            {
                "chemical": "",
                "weight_mg": null
            }
        ],
        "solvents": [
            {
                "solvent": "",
                "volume_ml": null
            }
        ],
        "stock_dispersion": "",
        "stock_volume_ml": null
    }
}
''')

PEROVSKITE_LAYER = json.loads(r'''
{
    "layer_type": "perovskite",
    "name": "Perovskite",
    "preset_id": "perovskite_spin_v1",
    "process": null,
    "role": "perovskite",
    "solution": {
        "formulation_type": "weighed_solids",
        "solids": [
            {
                "chemical": "",
                "weight_mg": null
            }
        ],
        "solvents": [
            {
                "solvent": "",
                "volume_ml": null
            }
        ],
        "stock_dispersion": "",
        "stock_volume_ml": null
    }
}
''')

PEROVSKITE_DEPOSITION_PROCESS = json.loads(r'''
{
    "anneal_steps": [
        {
            "seconds": 45,
            "temperature_c": 55
        },
        {
            "seconds": 90,
            "temperature_c": 60
        }
    ],
    "gas_backfill_stages": [],
    "method": "spin_coating_vcd",
    "spin_steps": [
        {
            "acceleration_rpm_per_s": 100,
            "rpm": 1000,
            "seconds": 10
        }
    ],
    "vcd_stages": [
        {
            "pressure_pa": 900,
            "seconds": 10,
            "valve": "VV02"
        },
        {
            "pressure_pa": 600,
            "seconds": 10,
            "valve": "VV02"
        },
        {
            "pressure_pa": 300,
            "seconds": 10,
            "valve": "VV02"
        }
    ]
}
''')


# The complete former factory catalogs, frozen as test data so the
# domain tests keep exercising the same stack/recipe variations.
# All fabrication parameters are synthetic placeholders (see docstring).

FACTORY_LAYER_PRESETS = json.loads(r'''
{
    "ag_evap_v1": {
        "label": "Ag — thermal evaporation",
        "layer": {
            "layer_type": "ag",
            "name": "Ag",
            "preset_id": "ag_evap_v1",
            "process": {
                "method": "thermal_evaporation",
                "rate_angstrom_per_s": 0.1,
                "thickness_nm": 10.0
            },
            "role": "top_electrode",
            "solution": null
        }
    },
    "bcp_evap_v1": {
        "label": "BCP — thermal evaporation",
        "layer": {
            "layer_type": "bcp",
            "name": "BCP",
            "preset_id": "bcp_evap_v1",
            "process": {
                "method": "thermal_evaporation",
                "rate_angstrom_per_s": 0.1,
                "thickness_nm": 10.0
            },
            "role": "etl",
            "solution": null
        }
    },
    "buried_interface_spin_v1": {
        "label": "SiO₂ nanoparticle — spin coating and annealing",
        "layer": {
            "layer_type": "sio2_np",
            "name": "SiO₂ nanoparticle",
            "preset_id": "buried_interface_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "buried_interface_modifier",
            "solution": {
                "formulation_type": "diluted_dispersion",
                "solids": [],
                "solvents": [
                    {
                        "solvent": "",
                        "volume_ml": null
                    }
                ],
                "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                "stock_volume_ml": null
            }
        }
    },
    "c60_evap_v1": {
        "label": "C60 — thermal evaporation",
        "layer": {
            "layer_type": "c60",
            "name": "C60",
            "preset_id": "c60_evap_v1",
            "process": {
                "method": "thermal_evaporation",
                "rate_angstrom_per_s": 0.1,
                "thickness_nm": 10.0
            },
            "role": "etl",
            "solution": null
        }
    },
    "edadi_spin_v1": {
        "label": "EDADI — spin coating",
        "layer": {
            "layer_type": "edadi",
            "name": "EDADI",
            "preset_id": "edadi_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "top_passivation",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "PEAI",
                        "weight_mg": 5.0
                    },
                    {
                        "chemical": "EDADI",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "IPA",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "niox_spin_v1": {
        "label": "NiOx — spin coating",
        "layer": {
            "layer_type": "niox",
            "name": "NiOx",
            "preset_id": "niox_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "htl",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "",
                        "weight_mg": null
                    }
                ],
                "solvents": [
                    {
                        "solvent": "",
                        "volume_ml": null
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "niox_sputter_v1": {
        "label": "NiOx — sputtering",
        "layer": {
            "layer_type": "niox",
            "name": "NiOx",
            "preset_id": "niox_sputter_v1",
            "process": {
                "duration_seconds": 30,
                "gas1": "Ar",
                "gas1_flow_sccm": 10.0,
                "gas2": "O2",
                "gas2_flow_sccm": 2.0,
                "method": "sputtering",
                "power_w": 40.0,
                "pressure_pa": 0.4,
                "sputter_mode": "rf"
            },
            "role": "htl",
            "solution": null
        }
    },
    "passivation_generic_v1": {
        "label": "Passivation — spin coating",
        "layer": {
            "layer_type": "passivation",
            "name": "Passivation",
            "preset_id": "passivation_generic_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "top_passivation",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "PEAI",
                        "weight_mg": 5.0
                    },
                    {
                        "chemical": "EDADI",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "IPA",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "passivation_spin_v1": {
        "label": "PEAI — spin coating",
        "layer": {
            "layer_type": "peai",
            "name": "PEAI",
            "preset_id": "passivation_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "top_passivation",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "PEAI",
                        "weight_mg": 5.0
                    },
                    {
                        "chemical": "EDADI",
                        "weight_mg": 5.0
                    }
                ],
                "solvents": [
                    {
                        "solvent": "IPA",
                        "volume_ml": 0.5
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "pcbm_spin_v1": {
        "label": "PCBM — spin coating",
        "layer": {
            "layer_type": "pcbm",
            "name": "PCBM",
            "preset_id": "pcbm_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "etl",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "",
                        "weight_mg": null
                    }
                ],
                "solvents": [
                    {
                        "solvent": "",
                        "volume_ml": null
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "perovskite_spin_v1": {
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        },
        "label": "Perovskite — spin coating and VCD",
        "layer": {
            "layer_type": "perovskite",
            "name": "Perovskite",
            "preset_id": "perovskite_spin_v1",
            "process": null,
            "role": "perovskite",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "",
                        "weight_mg": null
                    }
                ],
                "solvents": [
                    {
                        "solvent": "",
                        "volume_ml": null
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "sam_spin_v1": {
        "label": "SAM — spin coating",
        "layer": {
            "layer_type": "sam",
            "name": "SAM",
            "preset_id": "sam_spin_v1",
            "process": {
                "anneal_steps": [
                    {
                        "seconds": 45,
                        "temperature_c": 55
                    }
                ],
                "method": "spin_coating",
                "spin_steps": [
                    {
                        "acceleration_rpm_per_s": 100,
                        "rpm": 1000,
                        "seconds": 10
                    }
                ]
            },
            "role": "htl",
            "solution": {
                "formulation_type": "weighed_solids",
                "solids": [
                    {
                        "chemical": "",
                        "weight_mg": null
                    }
                ],
                "solvents": [
                    {
                        "solvent": "",
                        "volume_ml": null
                    }
                ],
                "stock_dispersion": "",
                "stock_volume_ml": null
            }
        }
    },
    "sno2_ald_v1": {
        "label": "SnO2 — ALD",
        "layer": {
            "layer_type": "sno2",
            "name": "SnO2",
            "preset_id": "sno2_ald_v1",
            "process": {
                "cycles": 50,
                "method": "ald",
                "substrate_temperature_c": 60.0,
                "thickness_nm": 10.0
            },
            "role": "etl",
            "solution": null
        }
    }
}
''')

FACTORY_BASELINE_SEEDS = json.loads(r'''
{
    "ito_niox_skip_pcbm_sno2_v1": {
        "label": "ITO / SAM / with PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_skip_pcbm_bcp_v1": {
        "label": "ITO / SAM / with PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_skip_no_pcbm_sno2_v1": {
        "label": "ITO / SAM / without PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_skip_no_pcbm_bcp_v1": {
        "label": "ITO / SAM / without PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_spin_pcbm_sno2_v1": {
        "label": "ITO / spin-coated NiOx / SAM / with PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_spin_pcbm_bcp_v1": {
        "label": "ITO / spin-coated NiOx / SAM / with PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_spin_no_pcbm_sno2_v1": {
        "label": "ITO / spin-coated NiOx / SAM / without PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_spin_no_pcbm_bcp_v1": {
        "label": "ITO / spin-coated NiOx / SAM / without PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_sputter_pcbm_sno2_v1": {
        "label": "ITO / sputtered NiOx / SAM / with PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_sputter_pcbm_bcp_v1": {
        "label": "ITO / sputtered NiOx / SAM / with PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_sputter_no_pcbm_sno2_v1": {
        "label": "ITO / sputtered NiOx / SAM / without PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "ito_niox_sputter_no_pcbm_bcp_v1": {
        "label": "ITO / sputtered NiOx / SAM / without PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "ITO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_skip_pcbm_sno2_v1": {
        "label": "FTO / SAM / with PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_skip_pcbm_bcp_v1": {
        "label": "FTO / SAM / with PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_skip_no_pcbm_sno2_v1": {
        "label": "FTO / SAM / without PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_skip_no_pcbm_bcp_v1": {
        "label": "FTO / SAM / without PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_spin_pcbm_sno2_v1": {
        "label": "FTO / spin-coated NiOx / SAM / with PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_spin_pcbm_bcp_v1": {
        "label": "FTO / spin-coated NiOx / SAM / with PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_spin_no_pcbm_sno2_v1": {
        "label": "FTO / spin-coated NiOx / SAM / without PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_spin_no_pcbm_bcp_v1": {
        "label": "FTO / spin-coated NiOx / SAM / without PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_sputter_pcbm_sno2_v1": {
        "label": "FTO / sputtered NiOx / SAM / with PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_sputter_pcbm_bcp_v1": {
        "label": "FTO / sputtered NiOx / SAM / with PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "pcbm",
                    "name": "PCBM",
                    "preset_id": "pcbm_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "etl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_sputter_no_pcbm_sno2_v1": {
        "label": "FTO / sputtered NiOx / SAM / without PCBM / SNO2",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "sno2",
                    "name": "SnO2",
                    "preset_id": "sno2_ald_v1",
                    "process": {
                        "cycles": 50,
                        "method": "ald",
                        "substrate_temperature_c": 60.0,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    },
    "fto_niox_sputter_no_pcbm_bcp_v1": {
        "label": "FTO / sputtered NiOx / SAM / without PCBM / BCP",
        "device_recipe": {
            "schema_version": 2,
            "setup_mode": "baseline",
            "junction_type": "single_junction",
            "perovskite_bandgap": "normal_bandgap",
            "tandem_type": null,
            "experimental_groups": [
                {
                    "group_id": "control",
                    "kind": "control",
                    "name": "Control",
                    "change_from_control": "Baseline fabrication procedure",
                    "inherits_control": false,
                    "adjustments": [],
                    "substrate_count": null
                },
                {
                    "group_id": "target-1",
                    "kind": "target",
                    "name": "Target 1",
                    "change_from_control": "",
                    "inherits_control": true,
                    "adjustments": [],
                    "layers": null,
                    "substrate_count": null
                }
            ],
            "substrate": {
                "material": "FTO",
                "vendor": "",
                "type_number": "",
                "width_mm": 15,
                "length_mm": 15
            },
            "layers": [
                {
                    "layer_type": "niox",
                    "name": "NiOx",
                    "preset_id": "niox_sputter_v1",
                    "process": {
                        "duration_seconds": 30,
                        "gas1": "Ar",
                        "gas1_flow_sccm": 10.0,
                        "gas2": "O2",
                        "gas2_flow_sccm": 2.0,
                        "method": "sputtering",
                        "power_w": 40.0,
                        "pressure_pa": 0.4,
                        "sputter_mode": "rf"
                    },
                    "role": "htl",
                    "solution": null
                },
                {
                    "layer_type": "sam",
                    "name": "SAM",
                    "preset_id": "sam_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "htl",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "sio2_np",
                    "name": "SiO₂ nanoparticle",
                    "preset_id": "buried_interface_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "buried_interface_modifier",
                    "solution": {
                        "formulation_type": "diluted_dispersion",
                        "solids": [],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "SiO₂ nanoparticle stock dispersion",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "perovskite",
                    "name": "Perovskite",
                    "preset_id": "perovskite_spin_v1",
                    "process": null,
                    "role": "perovskite",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "peai",
                    "name": "PEAI",
                    "preset_id": "passivation_spin_v1",
                    "process": {
                        "anneal_steps": [
                            {
                                "seconds": 45,
                                "temperature_c": 55
                            }
                        ],
                        "method": "spin_coating",
                        "spin_steps": [
                            {
                                "acceleration_rpm_per_s": 100,
                                "rpm": 1000,
                                "seconds": 10
                            }
                        ]
                    },
                    "role": "top_passivation",
                    "solution": {
                        "formulation_type": "weighed_solids",
                        "solids": [
                            {
                                "chemical": "",
                                "weight_mg": null
                            }
                        ],
                        "solvents": [
                            {
                                "solvent": "",
                                "volume_ml": null
                            }
                        ],
                        "stock_dispersion": "",
                        "stock_volume_ml": null
                    }
                },
                {
                    "layer_type": "c60",
                    "name": "C60",
                    "preset_id": "c60_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "bcp",
                    "name": "BCP",
                    "preset_id": "bcp_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "etl",
                    "solution": null
                },
                {
                    "layer_type": "ag",
                    "name": "Ag",
                    "preset_id": "ag_evap_v1",
                    "process": {
                        "method": "thermal_evaporation",
                        "rate_angstrom_per_s": 0.1,
                        "thickness_nm": 10.0
                    },
                    "role": "top_electrode",
                    "solution": null
                }
            ]
        },
        "deposition_process": {
            "anneal_steps": [
                {
                    "seconds": 45,
                    "temperature_c": 55
                },
                {
                    "seconds": 90,
                    "temperature_c": 60
                }
            ],
            "gas_backfill_stages": [],
            "method": "spin_coating_vcd",
            "spin_steps": [
                {
                    "acceleration_rpm_per_s": 100,
                    "rpm": 1000,
                    "seconds": 10
                }
            ],
            "vcd_stages": [
                {
                    "pressure_pa": 900,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 600,
                    "seconds": 10,
                    "valve": "VV02"
                },
                {
                    "pressure_pa": 300,
                    "seconds": 10,
                    "valve": "VV02"
                }
            ]
        }
    }
}
''')

