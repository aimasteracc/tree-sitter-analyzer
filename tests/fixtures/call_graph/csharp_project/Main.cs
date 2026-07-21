class Program
{
    static int LoadData()
    {
        return 1;
    }

    static int ProcessData(int data)
    {
        return data * 2;
    }

    static void Main()
    {
        int d = LoadData();
        ProcessData(d);
    }
}
