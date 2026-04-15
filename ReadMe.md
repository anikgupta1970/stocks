  # General (long-term trend view — daily candles)                                                                                                                                                             
  python3 main.py                                                                                                                                                                                              
  python3 main.py --mode general --top 20                                                                                                                                                                      
                                                                                                                                                                                                               
  # Intraday/swing (1-5 day trades — hourly candles with stop/target)                                                                                                                                          
  python3 main.py --mode intraday
  python3 main.py --mode intraday --top 20                                                                                                                                                                     
  python3 main.py --mode intraday --index nifty50 --top 10  
  python3 main.py --mode intraday --sector Banking    
