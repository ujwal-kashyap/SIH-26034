RULES = {

    "general": [

        {
            "id":
                "LM-MRP",

            "name":
                "Maximum Retail Price",

            "field":
                "MRP",

            "reference":
                "Rule 6",

            "required":
                True
        },

        {
            "id":
                "LM-NQ",

            "name":
                "Net Quantity",

            "field":
                "Net Quantity",

            "reference":
                "Rule 6",

            "required":
                True
        },

        {
            "id":
                "LM-MFR",

            "name":
                "Manufacturer / Packer / Importer",

            "field":
                "Manufacturer",

            "reference":
                "Rule 6",

            "required":
                True
        },

        {
            "id":
                "LM-ADDRESS",

            "name":
                "Address",

            "field":
                "Address",

            "reference":
                "Rule 6",

            "required":
                True
        },

        {
            "id":
                "LM-DATE",

            "name":
                "Manufacturing / Packing / Import information",

            "field":
                "Manufacturing Date",

            "reference":
                "Rule 6",

            "required":
                True
        },

        {
            "id":
                "LM-CARE",

            "name":
                "Consumer Care Details",

            "field":
                "Consumer Care",

            "reference":
                "Applicable declaration requirements",

            "required":
                True
        },

        {
            "id":
                "LM-UNIT",

            "name":
                "Unit Sale Price",

            "field":
                "Unit Sale Price",

            "reference":
                "Rule 6(11)",

            "required":
                False
        }
    ],


    "food": [

        {
            "id":
                "FOOD-FSSAI",

            "name":
                "FSSAI",

            "field":
                "FSSAI",

            "reference":
                "Food-specific screening",

            "required":
                False
        }
    ]
}


CATEGORY_MAP = {    

    "general":
        "general",

    "packaged_food":
        "food",

    "snacks":
        "food",

    "edible_oil":
        "food",

    "cosmetics":
        "general"
}
