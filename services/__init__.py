"""
Services package — business logic layer.

Routes delegate to services. Services use repositories for data access.
This keeps routes thin (validate → delegate → respond) and business logic testable.
"""
