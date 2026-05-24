Goal: Highly efficient receiving processing of delivered items.

Workflow:

1. User scans the shipping tracking bar code or types in a portion of the tracking number into the software.  
2. If there is one matching order in the queue, automatically open the receiving detail window for that order.   
3. User indicates the item has been received and that everything is as expected. Alternatively user marks the less than full quantity delivered. Alternatively the user indicates the item needs to be returned.  
4. Detail window closes and status of item is updated to “Received” or “Pending Returned” depending on outcome.  
5. User scans next item.

Requirements:

* Add a new field for purchase items that indicates the marketplace it will be sold on. Call it marketplace. Currently eBay and Amazon are the options. Marketplace value should not be set until the item is received.

Queue table view:

1. Separate mode from purchase items, but similar.  
2. Table columns should be the same as purchases.  
3. Filter list to items with “delivered” and “shipped untracked” status. This is the possible pool of items to be received.  
4. Search box with focus on load so search input can be entered immediately without clicking in the search field.  
5. All fields searchable. Primary will be tracking number.

Receiving detail view:

1. Large and easy to see window from a distance.  
2. Tracking number  
3. Carrier  
4. Order number  
5. If more than one item is in the same order, then include these fields for all items in the order on the detail screen  
6. Fields:  
   1. Main image from ebay listing.  
   2. Ebay title  
   3. Amazon title  
   4. Quantity expected  
7. Input options:  
   1. Quantity received field. Pre-filled with quantity ordered. (for each item in order)  
   2. Check box for return (for each item in order)  
   3. Pick list for Marketplace. Default is Amazon.  
   4. Received button which will save the information and close the window. Search box in queue screen is automatically receive focus.  
      1. If less than full quantity is received, then purchase item is split. Remaining quantity missing is added as a new item with the “No Tracking” status.  
      2. If return box is checked, then that item is marked with a new status called “Return Pending”  
      3. Otherwise all items marked with “Received” status. Save the marketplace selection.

