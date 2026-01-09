public class RotationPoint {

    public int RotationPointMethod(int[] array) {
        int low = 0;
        int high = array.length - 1;

        while (high >= low) {
            int mid = low + (high - low) / 2;

            // condition 1
            if (array[mid + 1] < array[mid])
                return mid + 1;

            // condition 2
            if (array[mid] < array[mid - 1])
                return mid;

            else if (array[mid] < array[high])
                high = mid - 1;

            else
                low = mid + 1;
        }

        // FIXME: Condition 2 should come after the 1st and not the opposite
        // else it will give the index out of bound exception in the cases where array
        // is shrinked to 2 positions.

        return -1;
    }

    public static void main(String[] args) {
        int[] array1 = { 66, 77, 88, 99, 11, 22, 33, 44, 55 };
        int[] array2 = { 99, 11, 22, 33, 44, 55 };
        int[] array3 = { 88, 99, 11, 22, 33, 44, 55 };
        int[] array4 = { 66, 77, 88, 99, 11, 22 };
        int[] array5 = { 88, 99, 11 };

        RotationPoint r = new RotationPoint();

        System.out.println(r.RotationPointMethod(array1));
        System.out.println(r.RotationPointMethod(array2));
        System.out.println(r.RotationPointMethod(array3));
        System.out.println(r.RotationPointMethod(array4));
        System.out.println(r.RotationPointMethod(array5));
    }
}
