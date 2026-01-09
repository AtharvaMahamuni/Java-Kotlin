public class BinarySearch {

    public int BinarySearchIterative(int[] array, int key) {

        int low = 0;
        int high = array.length - 1;

        while (high >= low) {
            int mid = (low + (high - low) / 2);

            if (array[mid] == key)
                return mid;

            if (array[mid] < key)
                low = mid + 1;

            else
                high = mid - 1;
        }

        return -1;
    }

    public int BinarySearchRecursive(int[] array, int key, int low, int high) {

        if (high < low)
            return -1;

        int mid = low + (high - low) / 2;

        if (key == array[mid])
            return mid;
        else if (key < array[mid])
            return BinarySearchRecursive(array, key, low, mid - 1);
        else
            return BinarySearchRecursive(array, key, mid + 1, high);

        // return -1;
    }

    public static void main(String[] args) {

        int[] array1 = { 11, 22, 33, 44, 55, 66, 77, 88, 99 };

        BinarySearch b = new BinarySearch();

        System.out.println("iterative");
        // Iterative
        System.out.println(b.BinarySearchIterative(array1, 33));
        System.out.println(b.BinarySearchIterative(array1, 99));
        System.out.println(b.BinarySearchIterative(array1, 11));
        System.out.println(b.BinarySearchIterative(array1, 666));

        System.out.println("recursive");
        // Recursive
        System.out.println(b.BinarySearchRecursive(array1, 33, 0, 8));
        System.out.println(b.BinarySearchRecursive(array1, 99, 0, 8));
        System.out.println(b.BinarySearchRecursive(array1, 11, 0, 8));
        System.out.println(b.BinarySearchRecursive(array1, 666, 0, 8));

    }

}
