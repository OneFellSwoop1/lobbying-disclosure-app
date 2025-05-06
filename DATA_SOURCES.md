# Data Sources

This document outlines the data sources that are currently implemented and those planned for future development.

## Active Data Sources

- **Senate LDA (Federal)**: Fully implemented using the ImprovedSenateLDADataSource class
  - Location: `data_sources/improved_senate_lda.py`
  - Status: Active and being used for all searches
  - API Documentation: https://lda.senate.gov/api/

## Planned Data Sources (Not Yet Implemented)

These data sources are included in the codebase but are not yet fully implemented or connected to the application:

1. **House Disclosures (Federal)**
   - Location: `data_sources/house_disclosures.py`
   - Status: Initial implementation, not connected
   - TODO: Complete implementation and connect to app.py

2. **New York State Lobbying**
   - Location: `data_sources/ny_state.py`
   - Status: Initial structure only, not implemented
   - TODO: Implement API integration and connect to app.py

3. **NYC Lobbying**
   - Location: `data_sources/nyc.py`
   - Status: Initial structure only, not implemented
   - TODO: Implement API integration and connect to app.py

## Legacy/Deprecated Data Sources

- `data_sources/senate_lda.py` - Original implementation, replaced by improved_senate_lda.py
- `data_sources/enhanced_senate_lda.py` - Alternative implementation, not used
- `data_sources/improved_senate_lda_backup.py` - Backup file of improved_senate_lda.py

## Future Development

To implement additional data sources:

1. Complete the implementation of each data source module
2. Ensure it extends the base `LobbyingDataSource` class from `data_sources/base.py`
3. Import and instantiate the data source in `app.py`
4. Add the appropriate conditional logic in search routes to use the correct data source
5. Update the UI to allow selecting different data sources
